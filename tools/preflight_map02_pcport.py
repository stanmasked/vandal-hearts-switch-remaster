#!/usr/bin/env python3
"""Read-only preflight for a user-owned US PC-port M_MAP02 runtime session.

This checks selected prerequisites documented by pinned upstream. It does not
build or run the game, extract copyrighted resources, or upload their bytes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

UPSTREAM_COMMIT = "14552fffa0e0b47e02b57592e274fc6e7a649923"
US_EXE_MD5 = "596bb082a2de5f1fe977dd3d7e160b03"
# From pinned platform/pc/tools/gen_kanji_font.py: US charset-2 glyphs 0..208.
KROM_US_BYTES = 209 * 30
KROM_US_SHA256 = "19b1dd839020e62a8a0f6dfc673c320da36105d9bc9bbce876aa151b7bd927a7"
BIOS_BYTES = 512 * 1024
BIOS_CHARSET2_OFFSET = 0x66000
REQUIRED_SOURCE_FILES = (
    "src/core/graphics.c",
    "src/states/game_setup.c",
    "platform/pc/Makefile",
    "platform/pc/tools/build_data_segment.py",
    "platform/pc/tools/gen_kanji_font.py",
)
PKG_CONFIG_REQUIRED = ("sdl2", "openal")
PKG_CONFIG_OPTIONAL = ("libwebp", "libavformat", "libavcodec", "libswscale", "libavutil")


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_disc_image(path: Path) -> tuple[bool, str]:
    """Check only raw CD sector structure and ISO9660 PVD, not ownership/region."""
    if not path.is_file():
        return False, "not a regular file"
    size = path.stat().st_size
    if size <= 17 * 2352 or size % 2352 != 0:
        return False, "expected raw 2352-byte CD sectors"
    with path.open("rb") as handle:
        handle.seek(16 * 2352 + 24)
        header = handle.read(7)
    if header != b"\x01CD001\x01":
        return False, "missing ISO9660 Mode 2 Form 1 volume descriptor"
    return True, "raw disc layout plausible (region and game content unverified)"



def identify_disc_boot_family(path: Path) -> str:
    """Classify the runtime boot/card-ID family, not the exact retail/localized release.

    A translated or patched disc can preserve the original PS-X EXE card ID.
    The exact US data-generator input is gated separately by the executable MD5.
    """
    data_offset = 24
    sector_size = 2352
    header_size = 0x800
    exe_vram = 0x80010000

    def read_bytes(handle, at: int, count: int) -> bytes:
        handle.seek(at)
        return handle.read(count)

    def card_id_offset(lba: int, vram: int) -> int:
        image_offset = (vram - exe_vram) + header_size
        return ((lba + image_offset // 2048) * sector_size
                + data_offset + image_offset % 2048)

    with path.open("rb") as handle:
        for lba, vram, identifiers in (
            (23, 0x800f5551, {
                b"BASLUS-00447VH": "USA",
                b"BISCPS-45183VH": "Asia",
            }),
            (15200, 0x800f76a9, {
                b"BISLPM-86007VH": "Japan",
            }),
        ):
            if read_bytes(handle, lba * sector_size + data_offset, 8) != b"PS-X EXE":
                continue
            ident = read_bytes(handle, card_id_offset(lba, vram), 14)
            if ident in identifiers:
                return identifiers[ident]
    return "unknown"


def identify_disc_release(path: Path) -> str:
    """Backward-compatible alias; returns only the boot/card-ID family."""
    return identify_disc_boot_family(path)


def _run(args, *, cwd=None):
    try:
        return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                              check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None


def inspect(upstream: Path, *, game_exe: Path | None = None,
            disc_image: Path | None = None, krom_source: Path | None = None,
            no_webp=False, no_hdvideo=False) -> dict:
    upstream = upstream.expanduser().resolve()
    blockers = []
    checks = {}
    if not upstream.is_dir():
        blockers.append("upstream_checkout_missing")
        checks["upstream"] = "missing"
    else:
        missing = [p for p in REQUIRED_SOURCE_FILES if not (upstream / p).is_file()]
        if missing:
            blockers.append("upstream_source_files_missing")
        checks["source_files_missing"] = missing
        git = shutil.which("git")
        rev = _run([git, "-C", str(upstream), "rev-parse", "HEAD"]) if git else None
        revision = rev.stdout.strip() if rev and rev.returncode == 0 else None
        checks["upstream_revision"] = revision
        if revision != UPSTREAM_COMMIT:
            blockers.append("upstream_revision_unverified")
        # A matching HEAD does not imply the source used by Make is pristine.
        # Ignore untracked files (the user's game resources are gitignored),
        # but reject edited, staged, deleted, or renamed tracked paths.
        status = _run([git, "-C", str(upstream), "status", "--porcelain",
                       "--untracked-files=no"]) if git else None
        if status is None or status.returncode != 0:
            checks["upstream_tracked_tree_clean"] = False
            checks["upstream_modified_tracked_paths"] = None
            blockers.append("upstream_tracked_tree_unverified")
        else:
            changed = [line[3:] for line in status.stdout.splitlines()
                       if len(line) >= 4]
            checks["upstream_tracked_tree_clean"] = not bool(changed)
            checks["upstream_modified_tracked_paths"] = changed
            if changed:
                blockers.append("upstream_tracked_tree_dirty")

    exe = game_exe or upstream / "SLUS_004.47"
    checks["game_executable_path"] = str(exe)
    if not exe.is_file():
        blockers.append("retail_executable_missing")
        checks["retail_executable_md5_matches"] = False
    else:
        digest = md5_file(exe)
        checks["retail_executable_md5"] = digest
        checks["retail_executable_md5_matches"] = digest == US_EXE_MD5
        if digest != US_EXE_MD5:
            blockers.append("retail_executable_md5_mismatch")

    default_krom = upstream / "external/psy-q/3.6/PSYQ/BIN/KROMDAT.BIN"
    krom = krom_source or Path(os.environ.get("VH_KROM_SOURCE") or default_krom)
    checks["krom_source_path"] = str(krom)
    checks["krom_source_present"] = krom.is_file()
    if not krom.is_file():
        blockers.append("krom_source_missing")
    else:
        size = krom.stat().st_size
        checks["krom_source_bytes"] = size
        checks["krom_source_layout"] = ("full_bios" if size == BIOS_BYTES
                                        else "kromdat")
        offset = BIOS_CHARSET2_OFFSET if size == BIOS_BYTES else 0
        if size < offset + KROM_US_BYTES:
            blockers.append("krom_source_too_small")
            checks["krom_charset2_sha256_matches"] = False
        else:
            with krom.open("rb") as handle:
                handle.seek(offset)
                font_data = handle.read(KROM_US_BYTES)
            actual_digest = hashlib.sha256(font_data).hexdigest()
            checks["krom_charset2_sha256"] = actual_digest
            checks["krom_charset2_sha256_matches"] = actual_digest == KROM_US_SHA256
            if actual_digest != KROM_US_SHA256:
                blockers.append("krom_charset2_sha256_mismatch")

    checks["disc_path"] = str(disc_image) if disc_image else None
    if disc_image is None:
        blockers.append("disc_image_not_specified")
        checks["disc_raw_layout_ok"] = False
    else:
        ok, detail = check_disc_image(disc_image)
        checks["disc_raw_layout_ok"] = ok
        checks["disc_check_detail"] = detail
        if not ok:
            blockers.append("disc_raw_layout_invalid")
        else:
            boot_family = identify_disc_boot_family(disc_image)
            checks["disc_boot_id_family"] = boot_family
            checks["disc_boot_id_accepted_by_us_runtime"] = boot_family in ("USA", "Asia")
            checks["disc_exact_retail_release_verified"] = False
            checks["disc_identification_basis"] = (
                "embedded PS-X EXE boot/card ID only; localized or patched content "
                "may retain this identifier"
            )
            if boot_family == "Japan":
                blockers.append("disc_region_not_supported_by_us_build")
            elif boot_family == "unknown":
                blockers.append("disc_boot_id_unrecognized")

    for executable in ("make", "cc", "pkg-config"):
        present = shutil.which(executable) is not None
        checks[executable + "_available"] = present
        if not present:
            blockers.append(executable + "_missing")

    if checks["pkg-config_available"]:
        deps = PKG_CONFIG_REQUIRED + (() if no_webp else ("libwebp",)) + (
            () if no_hdvideo else PKG_CONFIG_OPTIONAL[1:]
        )
        for dep in deps:
            result = _run(["pkg-config", "--exists", dep])
            present = result is not None and result.returncode == 0
            checks["pkg_" + dep] = present
            if not present:
                blockers.append("pkg_" + dep + "_missing")

    return {
        "kind": "map02_pcport_local_preflight",
        "pinned_upstream": UPSTREAM_COMMIT,
        "expected_us_executable_md5": US_EXE_MD5,
        "ready_for_attempt": not blockers,
        "blockers": blockers,
        "checks": checks,
        "notes": [
            "Read-only: no game resources extracted, copied, or uploaded.",
            "Tracked upstream source changes (staged or unstaged) block the pinned build; untracked user files are ignored.",
            "The disc boot/card ID identifies a runtime family, not the exact retail or localization build; patched images may preserve the ID.",
            "The boot/card ID probe mirrors pinned libcd.c and is not a full disc-integrity or ownership check.",
            "The exact US data-generator executable is gated separately by its retail MD5; a USA-family boot ID does not satisfy that gate.",
            "Passing does not prove a full compile, playable startup, or visible terrain pixels.",
            "KROM/BIOS verifies the exact US 209-glyph charset-2 SHA-256 required by the pinned generator.",
            "The game executable MD5 is the US data-generator requirement, not merely disc runtime region detection.",
            "For optional HD dependencies use --no-webp and --no-hdvideo with corresponding Makefile options.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="local pinned VandalHearts-PcPort checkout")
    parser.add_argument("--game-exe", type=Path, help="user-owned byte-exact US SLUS_004.47")
    parser.add_argument("--disc-image", type=Path, help="user-owned raw 2352-byte BIN disc")
    parser.add_argument("--krom-source", type=Path, help="user-owned KROMDAT.BIN or compatible BIOS font")
    parser.add_argument("--no-webp", action="store_true", help="disable optional libwebp requirement")
    parser.add_argument("--no-hdvideo", action="store_true", help="disable optional libav requirement")
    args = parser.parse_args()
    report = inspect(args.upstream, game_exe=args.game_exe,
                     disc_image=args.disc_image, krom_source=args.krom_source,
                     no_webp=args.no_webp, no_hdvideo=args.no_hdvideo)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ready_for_attempt"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
