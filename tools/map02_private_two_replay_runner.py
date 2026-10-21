#!/usr/bin/env python3
"""Run two sequential owner-LOCAL BizHawk capture attempts and audit them.

No original disc, BIOS, BK2, screenshots, private paths or hashes may be sent
to public CI. A successful run proves only the local file/log chain; neither
actual independent cold boots nor MAP02 identity is authenticated here.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from tools.map02_private_bk2_capture_plan import plan_lines, write_private_plan
from tools.map02_private_bizhawk_poweron_launch import SCRIPT
from tools.map02_private_disc_movie_preflight import (
    inspect_pair, read_private_full_bin_sha256,
)
from tools.map02_private_two_capture_audit import _private_root, audit_pair
from tools.verify_map02_private_neutral_capture_chain import verify


SCHEMA = "vh.map02.private-two-sequential-replays.v1"
PLAN_NAME = "vh-map02-review-plan.txt"
RUN_NAMES = ("vh-map02-cold-01", "vh-map02-cold-02")


def _no_existing_outputs(workspace: Path) -> None:
    for name in (PLAN_NAME, *RUN_NAMES):
        candidate = workspace / name
        if candidate.exists() or candidate.is_symlink():
            raise ValueError("private capture output already exists: never overwrite")


def _capture_dir(path: Path) -> None:
    # Do not rely on umask: apply owner-only permissions to newly-created
    # directories before an emulator can produce screenshots or logs.
    path.mkdir(mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
        info = path.stat()
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("private capture output directory must be owner-only")


def capture_twice(private_emuhawk: Path, private_disc: Path, private_bk2: Path,
                  private_workspace: Path, *,
                  expected_digest_file: Path | None = None,
                  max_windows: int = 4,
                  start: bool = False) -> dict:
    """Require explicit opt-in; run separate fresh emulator subprocesses.

    Output remains local. The capture chain and PNG files are independently
    checked after each process, and the second process is not attempted when
    the first is incomplete. The final auditor compares decoded image samples
    where it can, and never asserts original MAP02 authenticity.
    """
    workspace = _private_root(private_workspace)
    _no_existing_outputs(workspace)
    if type(max_windows) is not int or not 1 <= max_windows <= 10:
        raise ValueError("private capture window count must be 1..10")
    if type(start) is not bool:
        raise ValueError("private execution opt-in must be boolean")
    emulator = Path(private_emuhawk)
    if (not emulator.is_absolute() or not emulator.is_file()
            or not SCRIPT.is_absolute() or not SCRIPT.is_file()):
        raise ValueError("absolute EmuHawk executable and capture Lua are required")

    # Dry-run must genuinely inspect the source movie/disc rather than
    # reporting a misleading success based on just an empty workspace.
    # No output file or emulator process is created without --launch-two.
    digest = (read_private_full_bin_sha256(expected_digest_file)
              if expected_digest_file is not None else None)
    profile = inspect_pair(
        private_disc, private_bk2,
        verify_full_bin_sha256=digest is not None,
        expected_bin_sha256=digest,
    )
    if not profile["media_preflight_ready_for_owner_replay"]:
        raise ValueError("owner-private original media preflight failed")
    if not start:
        candidate = plan_lines(private_bk2, limit=max_windows)
        if len(candidate) < 6 or (len(candidate) - 3) % 3:
            raise ValueError("private BK2 candidate capture plan is malformed")
        return {
            "schema": SCHEMA,
            "explicit_launch_requested": False,
            "media_preflight_passed": True,
            "private_capture_plan_rows_checked": len(candidate) - 3,
            "full_bin_sha256_checked": digest is not None,
            "emulator_processes_started": 0,
            "capture_attempts_audited": 0,
            "owner_private_assets_uploaded": False,
            "original_map02_scene_authenticated": False,
        }

    plan = workspace / PLAN_NAME
    count = write_private_plan(
        private_bk2, plan, limit=max_windows,
    )
    if count < 3 or count % 3:
        raise ValueError("private capture plan contains invalid number of frames")

    for name in RUN_NAMES:
        output = workspace / name
        _capture_dir(output)
        argv = [
            sys.executable, "-m", "tools.map02_private_bizhawk_poweron_launch",
            str(private_emuhawk), str(private_disc), str(private_bk2),
            str(plan), str(output),
        ]
        if expected_digest_file is not None:
            argv += ["--private-full-bin-sha256-file", str(expected_digest_file)]
        argv.append("--launch")
        # The child wrapper redirects EmuHawk stdout/stderr (which contain
        # absolute private paths) into files in the private capture folder.
        # Suppress even the wrapper status on this outer public-safe terminal.
        process = subprocess.run(
            argv, check=False, shell=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if process.returncode != 0:
            raise ValueError("one private emulator capture process failed")
        # Reject an emulator that returned zero without the exact expected
        # Lua markers and structurally intact PNGs before starting the next.
        verify(private_bk2, plan, output / "vh_private_capture.log", output)

    paired = audit_pair(
        private_bk2, plan, workspace / RUN_NAMES[0], workspace / RUN_NAMES[1],
    )
    return {
        "schema": SCHEMA,
        "explicit_launch_requested": True,
        "emulator_processes_started": 2,
        "capture_attempts_audited": 2,
        "screenshot_pairs_checked": paired["screenshot_pairs_checked"],
        "matching_pixel_pairs": paired["decoded_pixel_equal_pairs"],
        "different_pixel_pairs": paired["decoded_pixel_different_pairs"],
        "unsupported_pixel_pairs": paired["decoded_pixel_unsupported_pairs"],
        "all_supported_png_pixel_content_equal":
            paired["all_supported_png_pixel_content_equal"],
        "owner_private_assets_uploaded": False,
        "independent_cold_boots_authenticated": False,
        "original_map02_scene_authenticated": False,
        "rendered_pixel_parity_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("absolute_emuhawk_executable", type=Path)
    parser.add_argument("owner_private_ps1_cue", type=Path)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_existing_empty_private_workspace", type=Path)
    parser.add_argument("--private-full-bin-sha256-file", type=Path)
    parser.add_argument("--max-windows", type=int, default=4)
    parser.add_argument("--launch-two", action="store_true",
                        help="Actually run TWO sequential local EmuHawk processes")
    args = parser.parse_args()
    try:
        report = capture_twice(
            args.absolute_emuhawk_executable,
            args.owner_private_ps1_cue, args.owner_private_bk2,
            args.owner_existing_empty_private_workspace,
            expected_digest_file=args.private_full_bin_sha256_file,
            max_windows=args.max_windows,
            start=args.launch_two,
        )
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        parser.error("private two-replay execution or capture audit failed")
    print(json.dumps(report, sort_keys=True, indent=2))
    if not args.launch_two:
        return 0
    return 0 if report["all_supported_png_pixel_content_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
