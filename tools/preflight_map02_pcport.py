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
        checks["krom_source_bytes"] = krom.stat().st_size
        if krom.stat().st_size < 0x30 + 1024:
            blockers.append("krom_source_too_small")

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
            "Passing does not prove a full compile, playable startup, region validity, or visible terrain pixels.",
            "KROM/BIOS presence does not verify its generator-specific content hash.",
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
