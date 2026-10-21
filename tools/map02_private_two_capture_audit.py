#!/usr/bin/env python3
"""Owner-only audit of two *supplied* private BK2/EmuHawk capture sessions.

This tool never starts the emulator or publishes paths, input, PNGs or hashes.
It does not prove a cold boot, Octoshock authenticity, MAP02 scene identity,
input/display alignment or rendered pixel equality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.verify_map02_private_neutral_capture_chain import (
    FRAME_COUNT, parse_plan, verify,
)
from tools.verify_map02_private_visual_candidates import read_png_private

SCHEMA = "vh.map02.private-two-capture-review.v1"


def _private_root(directory: Path) -> Path:
    root = Path(directory)
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise ValueError("owner capture requires an existing absolute nonsymlink directory")
    root = root.resolve(strict=True)
    for parent in (root, *root.parents):
        marker = parent / ".git"
        if marker.exists() or marker.is_symlink():
            raise ValueError("capture directories must remain outside Git")
    info = root.stat()
    if os.name != "nt":
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("owner capture directory must have owner-only permissions")
    return root


def audit_pair(movie: Path, plan: Path, first: Path, second: Path, *,
               minimum: int = 180, maximum: int = 1800,
               after: int = 1663, before: int = FRAME_COUNT) -> dict:
    """Require two distinct private capture chains and compare PNG file bytes.

    Byte differences can arise from PNG encoding/metadata; they are a review
    flag, NOT proof of a PS1 rendered-pixel mismatch. Matching PNG files do
    not independently prove the emulator executed a real original scene.
    """
    first_root = _private_root(first)
    second_root = _private_root(second)
    if first_root == second_root:
        raise ValueError("two captures must use separate private directories")

    # Independently authenticate the complete input/plan/log/PNG structure of
    # each supplied capture; the verifier reads the original local movie.
    parameters = dict(minimum=minimum, maximum=maximum, after=after, before=before)
    a = verify(movie, plan, first_root / "vh_private_capture.log",
               first_root, **parameters)
    b = verify(movie, plan, second_root / "vh_private_capture.log",
               second_root, **parameters)
    if a["screenshot_count"] != b["screenshot_count"]:
        raise ValueError("independent capture screenshot counts differ")
    _, rows = parse_plan(plan)
    if len(rows) != a["screenshot_count"]:
        raise ValueError("private plan/capture screenshot count mismatch")

    first_inodes = set()
    second_inodes = set()
    equal = 0
    for group, role, index, _ in rows:
        name = "vh_review_w%02d_%s_counter_%07d.png" % (
            group, role, index + 1,
        )
        p = first_root / name
        q = second_root / name
        p_info = os.stat(p, follow_symlinks=False)
        q_info = os.stat(q, follow_symlinks=False)
        if not stat.S_ISREG(p_info.st_mode) or not stat.S_ISREG(q_info.st_mode):
            raise ValueError("both captures must contain private regular PNG files")
        p_id = (p_info.st_dev, p_info.st_ino)
        q_id = (q_info.st_dev, q_info.st_ino)
        if (p_id == q_id or p_id in first_inodes or q_id in second_inodes
                or p_id in second_inodes or q_id in first_inodes):
            raise ValueError("capture sessions must not reuse screenshot inodes")
        first_inodes.add(p_id)
        second_inodes.add(q_id)
        first_bytes = read_png_private(first_root, name)
        second_bytes = read_png_private(second_root, name)
        if (os.stat(p, follow_symlinks=False).st_ino != p_info.st_ino
                or os.stat(q, follow_symlinks=False).st_ino != q_info.st_ino):
            raise ValueError("capture file replaced during comparison")
        equal += (hashlib.sha256(first_bytes).digest()
                  == hashlib.sha256(second_bytes).digest())

    return {
        "schema": SCHEMA,
        "two_private_capture_chains_passed": True,
        "distinct_capture_directories": True,
        "cross_run_png_inodes_distinct": True,
        "screenshot_pairs_checked": len(rows),
        "byte_identical_png_pairs": equal,
        "byte_different_png_pairs": len(rows) - equal,
        "all_png_file_bytes_identical": equal == len(rows),
        "byte_differences_require_manual_visual_review": equal != len(rows),
        "independent_cold_boots_authenticated": False,
        "actual_octoshock_playback_authenticated": False,
        "original_map02_scene_authenticated": False,
        "rendered_pixel_parity_verified": False,
        "source_asset_paths_or_hashes_reported": False,
        "owner_png_or_bk2_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_plan", type=Path)
    parser.add_argument("first_private_capture_directory", type=Path)
    parser.add_argument("second_private_capture_directory", type=Path)
    args = parser.parse_args()
    try:
        report = audit_pair(
            args.owner_private_bk2, args.owner_private_plan,
            args.first_private_capture_directory,
            args.second_private_capture_directory,
        )
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        parser.error("two private capture chains could not be verified")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["all_png_file_bytes_identical"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
