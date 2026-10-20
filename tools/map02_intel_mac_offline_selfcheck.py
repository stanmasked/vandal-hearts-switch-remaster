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
    ("test_map02_private_ft4_cli_mutations.py", 7),
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


def require_macos_deployment_target(target):
    """This experimental policy currently only attests 10.15 build metadata."""
    if target is not None and target != "10.15":
        raise ValueError("unsupported minimum macOS deployment target")
    return target


def macho_minos_is_target(otool_output: str, target: str) -> bool:
    """Parse only executable Mach-O deployment load commands, not text elsewhere."""
    for section in re.split(r"(?m)^Load command [0-9]+\\s*$", otool_output):
        if re.search(r"(?m)^\\s*cmd LC_BUILD_VERSION\\s*$", section):
            if re.search(r"(?m)^\\s*minos " + re.escape(target) +
                         r"(?:\\.0)?\\s*$", section):
                return True
        if re.search(r"(?m)^\\s*cmd LC_VERSION_MIN_MACOSX\\s*$", section):
            if re.search(r"(?m)^\\s*version " + re.escape(target) +
                         r"(?:\\.0)?\\s*$", section):
                return True
    return False


def run_synthetic_checks(raster: Path, *, deployment_target=None) -> dict:
    deployment_target = require_macos_deployment_target(deployment_target)
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
    if deployment_target is not None:
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment_target
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
        compile_command = [compiler]
        if deployment_target is not None:
            compile_command.extend(
                ["-arch", "x86_64", "-mmacosx-version-min=" + deployment_target]
            )
        compile_command.extend([
            "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            str(source), "-o", str(binary), "-lm",
        ])
        build = subprocess.run(
            compile_command, cwd=str(repo), env=env,
            text=True, capture_output=True, timeout=60,
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
        if deployment_target is not None:
            # This checks the recorded minimum OS version, not whether the
            # binary has actually been run on the older operating system.
            otool = shutil.which("otool")
            lipo = shutil.which("lipo")
            if not otool or not lipo:
                raise ValueError("Mach-O deployment verification tools unavailable")
            load = subprocess.run(
                [otool, "-l", str(binary)], cwd=str(repo),
                capture_output=True, text=True, timeout=30,
            )
            arch = subprocess.run(
                [lipo, "-archs", str(binary)], cwd=str(repo),
                capture_output=True, text=True, timeout=30,
            )
            if (load.returncode or arch.returncode or
                    arch.stdout.strip() != "x86_64" or
                    not macho_minos_is_target(load.stdout, deployment_target)):
                raise ValueError("Mach-O x86_64 minimum OS load command mismatch")

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
        "private_format_adversarial_cli_tests_passed": 7,
        "synthetic_regressions_total": cases,
        "synthetic_c11_ft4_frame_passed": True,
        "c11_macho_macos_minimum": deployment_target,
        "c11_macho_minimum_verified": deployment_target is not None,
        "catalina_10_15_runtime_executed": (
            deployment_target is not None and
            platform.mac_ver()[0].startswith("10.15")
        ),
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
    parser.add_argument(
        "--deployment-target", choices=("10.15",), default=None,
        help="also verify a C11 x86_64 Mach-O minimum-macOS-10.15 load command",
    )
    args = parser.parse_args()
    try:
        require_intel_mac()
        raster = pinned_public_raster(args.pinned_public_pc_raster)
        report = run_synthetic_checks(
            raster, deployment_target=args.deployment_target
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.error("Intel Mac offline synthetic MAP02 checks unavailable")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
