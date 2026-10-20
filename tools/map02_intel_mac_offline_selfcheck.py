#!/usr/bin/env python3
"""Asset-free offline Intel Mac readiness test for private MAP02 tooling.

Runs synthetic existing suites and real CLI subprocess probes; never opens an
original PS1 image, original texture, captured VRAM, or a private GPU log.
Requires an already acquired PUBLIC pinned PC-port pc_raster.c, and makes no
network connections. A successful receipt is not retail data authentication.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from tools.prepare_map02_pcport import git_blob_sha1
from tools.verify_map02_pc_vram4_equivalence import PINNED_RASTER_BLOB

SCHEMA = "vh.map02.intel-mac.offline-private-ft4-readiness.v1"
MAX_PUBLIC_BYTES = 2 * 1024 * 1024
SUITES = (
    ("test_verify_map02_private_timeline_pc_vram4.py", 14),
    ("test_verify_map02_private_pc_native_ft4.py", 25),
    ("test_map02_private_ft4_cli_contract.py", 3),
)


def require_intel_mac() -> None:
    """Fail closed: an x86 Linux VM or Apple Silicon is not Intel macOS."""
    if platform.system() != "Darwin" or platform.machine() != "x86_64":
        raise ValueError("offline checker requires macOS running on Intel x86_64")
    if sys.version_info[:2] < (3, 9):
        raise ValueError("offline checker requires Python 3.9 or newer")


def pinned_public_raster(path: Path) -> Path:
    """Never trust a moving or linked public reference file."""
    path = Path(path).absolute()
    if path.is_symlink() or not path.is_file():
        raise ValueError("pinned public raster must be a regular unlinked file")
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or
            info.st_size > MAX_PUBLIC_BYTES):
        raise ValueError("pinned public raster size or type invalid")
    if git_blob_sha1(path.read_bytes()) != PINNED_RASTER_BLOB:
        raise ValueError("pinned public raster source Git blob differs")
    return path


def run_synthetic_checks(raster: Path) -> dict:
    repo = Path(__file__).resolve().parent.parent
    compiler = shutil.which("clang")
    if not compiler:
        raise ValueError("local Clang compiler is required")
    env = dict(os.environ)
    # Keep the public CLI's --compiler value within its documented choices
    # ("gcc" or "clang"). Use the resolved binary path only for the direct
    # C11 build below; a full path is not a valid argparse choice.
    env["CC"] = "clang"
    env["MAP02_PINNED_RASTER"] = str(raster)
    cases = 0
    for suite, expected in SUITES:
        command = [
            sys.executable, "-m", "unittest", "discover", "-s", "tests",
            "-p", suite, "-v",
        ]
        completed = subprocess.run(
            command, cwd=str(repo), env=env, text=True,
            capture_output=True, timeout=240,
        )
        # Never print exception messages, test stdout/stderr or private paths.
        found = re.findall(r"Ran ([0-9]+) tests? in ", completed.stderr)
        if completed.returncode or found != [str(expected)]:
            raise ValueError("local synthetic MAP02 fixture regressions failed")
        cases += expected

    with tempfile.TemporaryDirectory(prefix="vh-map02-intel-mac-") as name:
        binary = Path(name) / "map02-ft4-check"
        source = repo / "tests/test_map02_vram4_frame.c"
        build = subprocess.run(
            [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             str(source), "-o", str(binary), "-lm"],
            cwd=str(repo), text=True, capture_output=True, timeout=60,
        )
        if build.returncode or not binary.is_file():
            raise ValueError("local synthetic MAP02 C11 frame build failed")
        run = subprocess.run(
            [str(binary)], cwd=str(repo), text=True,
            capture_output=True, timeout=60,
        )
        if (run.returncode or
                "frame-keyed VRAM4+GTE/FT4 original OT build" not in run.stdout):
            raise ValueError("local synthetic MAP02 C11 frame regression failed")

    if raster.is_symlink() or git_blob_sha1(raster.read_bytes()) != PINNED_RASTER_BLOB:
        raise ValueError("pinned public source changed during local tests")
    return {
        "schema": SCHEMA,
        "intel_macos_host_checked": True,
        "python_3_9_or_newer": True,
        "pinned_public_pc_raster_verified": True,
        "private_format_timeline_tests_passed": 14,
        "private_format_native_ft4_tests_passed": 25,
        "private_format_real_cli_tests_passed": 3,
        "synthetic_regressions_total": cases,
        "synthetic_c11_ft4_frame_passed": True,
        "external_network_used": False,
        "owner_ps1_disc_or_capture_read": False,
        "real_retail_map02_authenticated": False,
        "nintendo_switch_hardware_proven": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "pinned_public_pc_raster", type=Path,
        help="existing public pinned pc_raster.c; never pass game files",
    )
    args = parser.parse_args()
    try:
        require_intel_mac()
        raster = pinned_public_raster(args.pinned_public_pc_raster)
        report = run_synthetic_checks(raster)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("Intel Mac offline synthetic MAP02 checks unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
