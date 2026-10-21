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
from tools.map02_private_png_pixels import private_normalized_pixel_sha256

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
    """Compare both chain receipts and normalized PNG pixel content.

    Byte differences may be benign encoder or metadata changes; for supported
    RGB/RGBA 8-bit noninterlaced PNGs compare reconstructed pixels. Unsupported
    pixel formats stay unverified rather than pretending to be mismatches.
    This does not authenticate the original emulation or MAP02.
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
    # A different BizHawk frontend version or PSX TV standard means the two
    # screenshot sets are not directly comparable as one runtime profile.
    # These are self-reported Lua values, not independent core/BIOS proof.
    for field in ("reported_bizhawk_version", "reported_psx_display_standard"):
        if field not in a or field not in b or a[field] != b[field]:
            raise ValueError("two capture attempts report different emulator runtime profiles")
    # Two apparently identical frames may still be reached with different
    # cumulative core lag histories. Enforce equality when both local APIs
    # report samples. Never infer an Octoshock/BIOS identity from these counts.
    lag_first = a.get("reported_psx_lag_counts_at_snapshots")
    lag_second = b.get("reported_psx_lag_counts_at_snapshots")
    if (lag_first is None) != (lag_second is None):
        raise ValueError("two private PSX capture lag telemetry modes differ")
    lag_comparable = lag_first is not None
    if lag_comparable and lag_first != lag_second:
        raise ValueError("two private PSX capture lag timelines diverge")
    _, rows = parse_plan(plan)
    if len(rows) != a["screenshot_count"]:
        raise ValueError("private plan/capture screenshot count mismatch")

    first_inodes = set()
    second_inodes = set()
    equal = 0
    decoded_equal = 0
    decoded_different = 0
    decoded_unsupported = 0
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
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_size,
                    info.st_mtime_ns, info.st_ctime_ns)
        if (identity(os.stat(p, follow_symlinks=False)) != identity(p_info)
                or identity(os.stat(q, follow_symlinks=False)) != identity(q_info)):
            raise ValueError("capture file replaced or changed during comparison")
        file_bytes_match = (hashlib.sha256(first_bytes).digest()
                            == hashlib.sha256(second_bytes).digest())
        equal += file_bytes_match
        if file_bytes_match:
            # Both PNGs already passed full private-chain PNG validation.
            decoded_equal += 1
        else:
            first_pixels = private_normalized_pixel_sha256(first_bytes)
            second_pixels = private_normalized_pixel_sha256(second_bytes)
            if first_pixels is None or second_pixels is None:
                decoded_unsupported += 1
            elif first_pixels == second_pixels:
                decoded_equal += 1
            else:
                decoded_different += 1

    return {
        "schema": SCHEMA,
        "two_private_capture_chains_passed": True,
        "same_reported_bizhawk_runtime_profile": True,
        "same_reported_psx_lag_timeline": lag_comparable,
        "psx_lag_counter_available_in_both": lag_comparable,
        "psx_lag_timeline_proves_controller_delivery": False,
        "octoshock_core_identity_authenticated": False,
        "distinct_capture_directories": True,
        "cross_run_png_inodes_distinct": True,
        "screenshot_pairs_checked": len(rows),
        "byte_identical_png_pairs": equal,
        "byte_different_png_pairs": len(rows) - equal,
        "all_png_file_bytes_identical": equal == len(rows),
        "decoded_pixel_equal_pairs": decoded_equal,
        "decoded_pixel_different_pairs": decoded_different,
        "decoded_pixel_unsupported_pairs": decoded_unsupported,
        "all_supported_png_pixel_content_equal": (
            decoded_different == 0 and decoded_unsupported == 0),
        "byte_differences_require_manual_visual_review": equal != len(rows),
        "unresolved_pixel_differences_require_manual_review": (
            decoded_different > 0 or decoded_unsupported > 0),
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
    return 0 if report["all_supported_png_pixel_content_equal"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
