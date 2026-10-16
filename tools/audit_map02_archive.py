#!/usr/bin/env python3
"""Read-only local M_MAP02 audit of a user-owned 7z disc archive.

Select one archived PS1 BIN/ISO, stream it to a private temporary file
under a fixed basename (never use archive paths), audit the bounded sector
ranges, then delete the temporary file. Report only metadata/hashes and
the two target GFX indices. No proprietary bytes are sent to GitHub.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from tools.audit_map02_disc_prs import (
    DAT_SECTOR_COUNT, DAT_START_SECTOR, PRIOR_DAT_LENGTH,
    SECTOR_COUNT, START_SECTOR, USER_BYTES, RAW_BYTES, audit_prs,
    read_sectors,
)

MAX_DISC_BYTES = 1024 * 1024 * 1024
DISC_SUFFIXES = (".bin", ".iso", ".img")


def sevenzip_binary(explicit=None):
    if explicit is not None:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError("7z executable not found")
        return str(path)
    for candidate in ("7zz", "7z", "7za"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise ValueError("7z/7zz is required locally to inspect an owned archive")


def archive_members(archive: Path, sevenzip: str) -> list[dict]:
    # 7z's -slt output has an archive header before '----------',
    # then one record per archived member.
    result = subprocess.run(
        [sevenzip, "l", "-slt", "-bd", str(archive)],
        capture_output=True, text=True, errors="replace",
        timeout=120, check=False,
    )
    if result.returncode != 0:
        raise ValueError("7z cannot list archive members (corrupt/password-protected?)")
    if "----------" not in result.stdout:
        raise ValueError("7z listing missing member metadata delimiter")
    records = result.stdout.split("----------", 1)[1].strip().split("\n\n")
    parsed = []
    for record in records:
        fields = {}
        for line in record.splitlines():
            if " = " in line:
                key, value = line.split(" = ", 1)
                fields[key] = value.strip()
        if not fields.get("Path") or fields.get("Folder") == "+":
            continue
        if "Size" not in fields or not re.fullmatch(r"[0-9]+", fields["Size"]):
            continue
        parsed.append({"path": fields["Path"], "size": int(fields["Size"])})
    return parsed


def pick_disc_member(members: list[dict], explicit: str | None) -> dict:
    if explicit is None:
        candidates = [entry for entry in members
                      if entry["path"].lower().endswith(DISC_SUFFIXES)]
        if len(candidates) != 1:
            raise ValueError(
                f"expected one disc BIN/ISO/IMG in archive, found {len(candidates)}; "
                "pass --member to choose the intended disc track"
            )
        entry = candidates[0]
    else:
        matching = [entry for entry in members if entry["path"] == explicit]
        if len(matching) != 1:
            raise ValueError("named disc member is not uniquely present in archive")
        entry = matching[0]
    if entry["size"] <= 0 or entry["size"] > MAX_DISC_BYTES:
        raise ValueError("disc member size outside safe 1 GiB audit limit")
    # 7z accepts glob-style archived member selectors. Do not allow
    # wildcard expansion to extract a different or multiple member.
    if any(ch in entry["path"] for ch in "*?[]"):
        raise ValueError("ambiguous wildcard characters in disc member path")
    return entry


def stream_member_to_file(archive: Path, member: dict, sevenzip: str,
                          destination: Path) -> int:
    command = [sevenzip, "x", "-so", "-bd", str(archive), member["path"]]
    count = 0
    # Fixed private path prevents any archive path traversal. Raw game data
    # exists only in a TemporaryDirectory and is never printed or committed.
    with destination.open("xb") as handle:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        try:
            for chunk in iter(lambda: proc.stdout.read(65536), b""):
                count += len(chunk)
                if count > member["size"] or count > MAX_DISC_BYTES:
                    raise ValueError("7z extracted more bytes than declared disc member")
                handle.write(chunk)
            if proc.wait(timeout=120) != 0:
                raise ValueError("7z disc member extraction failed")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=30)
            if proc.stdout is not None:
                proc.stdout.close()
    if count != member["size"]:
        raise ValueError("extracted disc member size differs from 7z listing")
    return count


def audit_archive(archive: Path, *, member_name=None, layout="mode2-2352",
                  sector_bias=0, with_dat=True, sevenzip=None) -> dict:
    archive = archive.expanduser().resolve(strict=True)
    if not archive.is_file():
        raise ValueError("archive path must be a file")
    tool = sevenzip_binary(sevenzip)
    members = archive_members(archive, tool)
    member = pick_disc_member(members, member_name)
    sector_size = RAW_BYTES if layout == "mode2-2352" else USER_BYTES
    if layout not in ("mode2-2352", "iso-2048"):
        raise ValueError("layout must be mode2-2352 or iso-2048")
    required_last = (DAT_START_SECTOR + DAT_SECTOR_COUNT if with_dat
                     else START_SECTOR + SECTOR_COUNT) + sector_bias
    if required_last < 0 or member["size"] < required_last * sector_size:
        raise ValueError("archived disc too short for expected map sector table")
    with tempfile.TemporaryDirectory(prefix="vh-map02-archive-") as temp:
        disc = Path(temp) / "owned-disc-temporary.bin"
        size = stream_member_to_file(archive, member, tool, disc)
        prs = read_sectors(disc, layout, sector_bias)
        dat = (read_sectors(disc, layout, sector_bias,
                            start_sector=DAT_START_SECTOR,
                            sector_count=DAT_SECTOR_COUNT)[:PRIOR_DAT_LENGTH]
               if with_dat else None)
        result = audit_prs(prs, dat=dat)
    result.update({
        "input_type": "local_user_owned_7z_archive",
        "archive_name": archive.name,
        "archive_bytes": archive.stat().st_size,
        "member_name": member["path"],
        "member_bytes": size,
        "disc_layout": layout,
        "sector_bias": sector_bias,
        "prs_start_sector": START_SECTOR,
        "dat_start_sector": DAT_START_SECTOR if with_dat else None,
        "original_archive_modified": False,
        "temporary_disc_deleted": True,
        "evidence_scope": (
            "read-only disc resource hashes and GFX; "
            "not a PC-port gameplay trace or visible framebuffer pixels"
        ),
    })
    if with_dat:
        result["dat_source"] = "same_disc_archive"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="user-owned local .7z file")
    parser.add_argument("--member", help="exact member path when multiple discs exist")
    parser.add_argument("--layout", required=True, choices=("mode2-2352", "iso-2048"))
    parser.add_argument("--sector-bias", type=int, default=0)
    parser.add_argument("--without-dat", action="store_true")
    parser.add_argument("--sevenzip", type=Path,
                        help="local 7z/7zz executable, for testable explicit selection")
    parser.add_argument("--require-prior-provenance", action="store_true",
                        help="fail if archived original US PRS/DAT hashes differ")
    args = parser.parse_args()
    try:
        result = audit_archive(
            args.archive, member_name=args.member, layout=args.layout,
            sector_bias=args.sector_bias, with_dat=not args.without_dat,
            sevenzip=args.sevenzip,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    provenance_ok = (
        result["matches_prior_logical_compressed_sha256"]
        and result["matches_prior_decompressed_sha256"]
        and result["matches_prior_target_gfx"]
        and (args.without_dat or
             (result["dat_comparison"]["matches_prior_disc_audit_with_provenance"]
              and result["dat_comparison"]["matches_prior_dat_sha256"]))
    )
    return int(args.require_prior_provenance and not provenance_ok)


if __name__ == "__main__":
    raise SystemExit(main())
