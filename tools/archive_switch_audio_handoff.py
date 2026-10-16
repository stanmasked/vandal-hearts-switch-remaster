#!/usr/bin/env python3
"""Stage 223: portable, bounded ZIP with detached SHA-256 handoff verification.

The archive is created exclusively from original NRO/CSV evidence, an operator
record, and session cards already checked by stage 222. On another computer
the ZIP can be validated against its SHA-256 communicated independently,
then safely unpacked into a temporary directory and re-audited.

No cryptographic signature, hardware PASS, SD durability or authentic
operator identity is implied. No evidence originals are modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import zipfile

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as first_run
import audit_switch_audio_handoff as handoff
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-handoff-archive/v1"
INDEX_NAME = "archive-index.json"
MAX_ZIP = 256 * 1024 * 1024
MAX_ITEM = 128 * 1024 * 1024
MAX_INDEX = 64 * 1024
MAX_ENTRIES = 150
MAX_TOTAL = 256 * 1024 * 1024
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")


class ArchiveError(ValueError):
    """Untrusted/altered archive, unsafe member, or invalid anchor."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ArchiveError(message)


def digest(path: Path) -> dict:
    size, sha = bundle.digest_file(path)
    return {"size": size, "sha256": sha}


def safe_name(name: object) -> str:
    require(isinstance(name, str) and name and len(name) <= 512,
            "ZIP entry has invalid name")
    require(not name.startswith("/") and "\\" not in name and
            ":" not in name and "\x00" not in name and
            all(ord(ch) >= 32 for ch in name) and
            all(part not in ("", ".", "..") for part in name.split("/")),
            "unsafe ZIP member path")
    require(name == INDEX_NAME or name == "operator.json" or
            (name.startswith("bundle/") and len(name) > 7) or
            (name.startswith("cards/") and name.endswith(".json") and
             len(name.split("/")) == 2),
            "unexpected ZIP member namespace")
    return name


def json_bytes(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False,
                       indent=2) + "\n").encode("utf-8")


def decode_index(data: bytes) -> dict:
    require(len(data) <= MAX_INDEX, "archive index exceeds 64 KiB")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"invalid archive index: {exc}") from exc
    require(isinstance(obj, dict) and
            set(obj) == {"schema", "hardware_status", "git_sha", "review_result",
                         "require_h06", "compare_builds", "members"} and
            obj["schema"] == SCHEMA and
            obj["hardware_status"] == bundle.HARDWARE_STATUS,
            "unknown archive index schema or claimed hardware PASS")
    require(isinstance(obj["git_sha"], str) and
            bundle.GIT_SHA_RE.fullmatch(obj["git_sha"]) is not None,
            "invalid indexed Git SHA")
    require(obj["review_result"] in
            ("INVESTIGATE", "INCONCLUSIVE", "READY_FOR_INDEPENDENT_MANUAL_REVIEW") and
            isinstance(obj["review_result"], str),
            "invalid indexed review outcome")
    for field in ("require_h06", "compare_builds"):
        require(type(obj[field]) is bool, f"invalid index option {field}")
    members = obj["members"]
    require(isinstance(members, list) and
            3 <= len(members) <= MAX_ENTRIES - 1,
            "invalid archive index member count")
    seen = set()
    for entry in members:
        require(isinstance(entry, dict) and set(entry) == {"name", "size", "sha256"},
                "invalid indexed member")
        name = safe_name(entry["name"])
        require(name not in seen and name != INDEX_NAME,
                "duplicate archive index member")
        seen.add(name)
        require(type(entry["size"]) is int and 0 <= entry["size"] <= MAX_ITEM and
                isinstance(entry["sha256"], str) and
                SHA_RE.fullmatch(entry["sha256"]) is not None,
                "invalid indexed size or digest")
    require("operator.json" in seen and
            "bundle/" + bundle.MANIFEST_NAME in seen and
            any(name.endswith(".nro") and name.startswith("bundle/") for name in seen),
            "indexed evidence essentials missing")
    return obj


def zip_entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    return info


def source_files(root: Path, observations: Path, cards: Path, report: dict) -> list[tuple[str, Path]]:
    require(root.is_dir() and not root.is_symlink(), "source bundle must be a directory")
    require(not cards.is_symlink(), "cards directory may not be a symbolic link")
    require(not observations.is_symlink(), "operator observations may not be a symlink")
    manifest = bundle.read_manifest(root)
    files: list[tuple[str, Path]] = [
        ("bundle/" + bundle.MANIFEST_NAME, root / bundle.MANIFEST_NAME),
        ("bundle/" + manifest["nro"]["path"],
         bundle.safe_member(root, manifest["nro"]["path"], ".nro")),
    ]
    files += [("bundle/" + x["path"], bundle.safe_member(root, x["path"], ".csv"))
              for x in manifest["sessions"]]
    files += [("operator.json", observations)]
    for record in report["session_cards"]:
        if record["status"] != "MISSING_MANUAL_CARD":
            name = record["card"]
            files.append(("cards/" + name, cards / name))
    require(3 <= len(files) <= MAX_ENTRIES - 1, "too many archived source files")
    require(len({x[0] for x in files}) == len(files), "repeated archive member")
    for name, path in files:
        safe_name(name)
        require(path.is_file() and not path.is_symlink(),
                f"source missing or symlinked: {name}")
    return files


def verify_archive(archive: Path, expected_sha256: str) -> dict:
    """Hash ZIP itself first, then independently verify every member and audit."""
    require(isinstance(expected_sha256, str) and
            SHA_RE.fullmatch(expected_sha256) is not None,
            "--expected-sha256 must be an independent 64-hex SHA-256 anchor")
    require(archive.is_file() and not archive.is_symlink(),
            "archive missing or a symbolic link")
    size = archive.stat().st_size
    require(0 < size <= MAX_ZIP, "archive outside allowed size limit")
    archive_digest = digest(archive)
    require(archive_digest["sha256"] == expected_sha256,
            "ARCHIVE_SHA256_MISMATCH: transferred ZIP differs from detached SHA-256")
    try:
        with zipfile.ZipFile(archive, "r") as z:
            all_info = z.infolist()
            require(1 < len(all_info) <= MAX_ENTRIES, "invalid ZIP member count")
            entries = {}
            total = 0
            for info in all_info:
                name = safe_name(info.filename)
                require(name not in entries, "duplicate ZIP member path")
                entries[name] = info
                mode = info.external_attr >> 16
                require(not info.is_dir() and not stat.S_ISLNK(mode) and
                        (not mode or stat.S_ISREG(mode)),
                        "ZIP directory, symlink or special member forbidden")
                require(not (info.flag_bits & 1) and
                        info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                        "encrypted or unsupported compressed ZIP member")
                limit = MAX_INDEX if name == INDEX_NAME else MAX_ITEM
                require(0 <= info.file_size <= limit, "oversized ZIP entry")
                total += info.file_size
                require(total <= MAX_TOTAL, "expanded ZIP is too large")
            require(INDEX_NAME in entries, "archive missing integrity index")
            with z.open(entries[INDEX_NAME]) as stream:
                index = decode_index(stream.read(MAX_INDEX + 1))
            members = {x["name"]: x for x in index["members"]}
            require(set(entries) == set(members) | {INDEX_NAME},
                    "ZIP file list disagrees with integrity index")
            # Unpack only verified bounded files to a private temporary folder.
            # Never extract untrusted names using ZipFile.extractall().
            with tempfile.TemporaryDirectory(prefix="vh-switch-audio-check-") as temp:
                temp_root = Path(temp)
                (temp_root / "cards").mkdir()
                for name in sorted(members):
                    info = entries[name]
                    expected = members[name]
                    require(info.file_size == expected["size"],
                            f"ZIP declared size differs from index: {name}")
                    target = temp_root.joinpath(*name.split("/"))
                    require(target.resolve().is_relative_to(temp_root.resolve()),
                            "unsafe temporary member path")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    size_read = 0
                    h = hashlib.sha256()
                    with z.open(info, "r") as source, target.open("xb") as output:
                        while block := source.read(1024 * 1024):
                            size_read += len(block)
                            require(size_read <= expected["size"],
                                    f"ZIP member grew beyond indexed size: {name}")
                            h.update(block)
                            output.write(block)
                    require(size_read == expected["size"] and
                            h.hexdigest() == expected["sha256"],
                            f"ZIP_MEMBER_SHA256_MISMATCH: {name}")
                report = handoff.audit(
                    temp_root / "bundle", temp_root / "operator.json",
                    temp_root / "cards", require_h06=index["require_h06"],
                    compare_builds=index["compare_builds"])
                require(report["build"]["git_sha_self_reported"] == index["git_sha"] and
                        report["result"] == index["review_result"],
                        "ZIP audit differs from archived Git SHA or review result")
                return {
                    "schema": SCHEMA,
                    "result": "ARCHIVE_BYTES_AND_EVIDENCE_REVERIFIED",
                    "hardware_status": bundle.HARDWARE_STATUS,
                    "archive_sha256": archive_digest["sha256"],
                    "archive_bytes": archive_digest["size"],
                    "member_count": len(members),
                    "member_inventory": sorted(index["members"], key=lambda x: x["name"]),
                    "git_sha_self_reported": index["git_sha"],
                    "handoff_review": report["result"],
                    "scenario_statuses": {
                        row["id"]: row["status"] for row in report["acceptance_matrix"]
                    },
                    "retest_scenarios": [
                        row["scenario"] for row in report["retests"]
                    ],
                    "session_claims": report["repeated_session_claims"],
                    "manual_signoff": "REQUIRED_NOT_AUTOMATED",
                    "limitations": (
                        "Independent ZIP hash authenticates no operator, console or "
                        "source unless the original SHA-256 was safely preserved "
                        "out of band. Exact bytes and internal consistency do not "
                        "constitute a signed attestation or physical hardware PASS."
                    ),
                }
    except (zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise ArchiveError(f"damaged ZIP archive: {exc}") from exc


def create_archive(root: Path, observations: Path, cards: Path, output: Path,
                   *, require_h06: bool = False, compare_builds: bool = False) -> dict:
    root = root.resolve()
    require(output.parent.is_dir(), "archive output parent directory missing")
    require(not output.exists() and not output.is_symlink(),
            "archive output already exists; refusing overwrite")
    require(not output.absolute().resolve().is_relative_to(root) and
            not output.absolute().resolve().is_relative_to(cards.resolve()),
            "archive output must remain outside source bundle and cards")
    require(output.absolute() != observations.absolute(),
            "archive output must not overwrite operator observations")
    report = handoff.audit(root, observations, cards,
                           require_h06=require_h06, compare_builds=compare_builds)
    sources = source_files(root, observations, cards, report)
    inventory = []
    for name, source in sources:
        item = digest(source)
        require(item["size"] <= MAX_ITEM, f"evidence file exceeds ZIP limits: {name}")
        inventory.append({"name": name, **item})
    index = {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "git_sha": report["build"]["git_sha_self_reported"],
        "review_result": report["result"],
        "require_h06": require_h06,
        "compare_builds": compare_builds,
        "members": inventory,
    }
    require(len(json_bytes(index)) <= MAX_INDEX, "archive index too large")
    handle = tempfile.NamedTemporaryFile(
        prefix=".vh-switch-handoff-", suffix=".tmp",
        dir=output.parent, delete=False)
    tmp = Path(handle.name)
    handle.close()
    try:
        with zipfile.ZipFile(tmp, "w", allowZip64=True) as z:
            for name, source in sources:
                with source.open("rb") as input_file, z.open(zip_entry(name), "w") as dest:
                    shutil.copyfileobj(input_file, dest, length=1024 * 1024)
            z.writestr(zip_entry(INDEX_NAME), json_bytes(index))
        require(tmp.stat().st_size <= MAX_ZIP, "created ZIP exceeds archive size limit")
        original_sha = digest(tmp)["sha256"]
        checked = verify_archive(tmp, original_sha)
        require(checked["result"] == "ARCHIVE_BYTES_AND_EVIDENCE_REVERIFIED",
                "newly produced ZIP did not pass strict readback")
        # hard-link publish is exclusive: it will not overwrite an archive
        # previously placed at output by the user or another process.
        os.link(tmp, output)
        return {"result": "ARCHIVE_CREATED_AND_REVERIFIED",
                "hardware_status": bundle.HARDWARE_STATUS,
                "archive_sha256": original_sha,
                "archive_bytes": tmp.stat().st_size,
                "member_count": len(inventory),
                "handoff_review": checked["handoff_review"],
                "out_of_band_sha256_required": True,
                "manual_signoff": "REQUIRED_NOT_AUTOMATED"}
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create", help="write and reverify a portable ZIP")
    create.add_argument("bundle", type=Path)
    create.add_argument("--observations", required=True, type=Path)
    create.add_argument("--cards-dir", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--require-h06", action="store_true")
    create.add_argument("--compare-builds", action="store_true")
    check = actions.add_parser("verify", help="verify transferred ZIP with detached SHA256")
    check.add_argument("archive", type=Path)
    check.add_argument("--expected-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "create":
            response = create_archive(
                args.bundle, args.observations, args.cards_dir, args.output,
                require_h06=args.require_h06, compare_builds=args.compare_builds)
        else:
            response = verify_archive(args.archive, args.expected_sha256)
    except (ArchiveError, handoff.HandoffError, first_run.OperatorError,
            bundle.BundleError, audio.LogFormatError, OSError, TypeError,
            KeyError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
