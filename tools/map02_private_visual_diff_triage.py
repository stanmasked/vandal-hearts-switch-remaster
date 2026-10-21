#!/usr/bin/env python3
"""Owner-private RGB screenshot difference triage after full BK2 chain audit.

Differences reveal visible pixel change ONLY. They do not establish MAP02,
a scene transition, correct PS1 display timing, or real emulator execution.
Never upload the private frame-index report, screenshots, inputs or game.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat

from tools.verify_map02_private_neutral_capture_chain import (
    verify as verify_chain, parse_plan,
)
from tools.verify_map02_private_visual_candidates import read_png_private
from tools.map02_private_png_visual_diff import (
    decode_private_rgb8, compare_private_rgb8,
)

SCHEMA = "vh.map02.private-visual-diff-triage.v1"


def triage(private_bk2: Path, private_plan: Path, private_log: Path,
           png_root: Path, *, minimum=180, maximum=1800, after=1663,
           before=933949, pixel_threshold=32) -> dict:
    if type(pixel_threshold) is not int or not 0 <= pixel_threshold <= 254:
        raise ValueError("invalid per-pixel delta threshold")
    proof = verify_chain(
        private_bk2, private_plan, private_log, png_root,
        minimum=minimum, maximum=maximum, after=after, before=before,
    )
    _, items = parse_plan(private_plan)
    groups = {}
    for group, role, index, _ in items:
        groups.setdefault(group, {})[role] = index
    reviewed = []
    for group in sorted(groups):
        indices = groups[group]
        pixels = {}
        dimensions = None
        for role in ("before", "middle", "after"):
            frame = indices[role]
            filename = "vh_review_w%02d_%s_counter_%07d.png" % (
                group, role, frame + 1,
            )
            pixels[role] = decode_private_rgb8(read_png_private(png_root, filename))
            current_size = pixels[role][:2]
            if dimensions is not None and dimensions != current_size:
                raise ValueError("screenshot dimension differs inside one candidate interval")
            dimensions = current_size
        before_middle = compare_private_rgb8(
            pixels["before"], pixels["middle"], threshold=pixel_threshold)
        middle_after = compare_private_rgb8(
            pixels["middle"], pixels["after"], threshold=pixel_threshold)
        before_after = compare_private_rgb8(
            pixels["before"], pixels["after"], threshold=pixel_threshold)
        maximum_delta = max(
            before_middle["fraction_pixels_above_threshold"],
            middle_after["fraction_pixels_above_threshold"],
        )
        # This status means only prominent *unmasked pixel difference*.
        # Animation, OSD, filters and even menus can cause it.
        prominent = (
            maximum_delta >= 0.25 and
            max(before_middle["mean_absolute_rgb_channel_delta"],
                middle_after["mean_absolute_rgb_channel_delta"]) >= 24
        )
        reviewed.append({
            "review_group": group,
            "zero_based_input_indices": [
                indices["before"], indices["middle"], indices["after"]
            ],
            "screenshot_dimensions": list(dimensions),
            "before_to_middle": before_middle,
            "middle_to_after": middle_after,
            "before_to_after": before_after,
            "prominent_unmasked_pixel_difference": prominent,
            "actual_scene_transition_verified": False,
        })
    reviewed.sort(key=lambda row: (
        -max(row["before_to_middle"]["fraction_pixels_above_threshold"],
             row["middle_to_after"]["fraction_pixels_above_threshold"]),
        row["zero_based_input_indices"][0],
    ))
    return {
        "schema": SCHEMA,
        "screenshot_count": proof["screenshot_count"],
        "all_capture_metadata_and_png_integrity_checked": True,
        "supported_png_pixels_decoded": True,
        "pixel_difference_threshold": pixel_threshold,
        "rank_basis": "fraction_of_changed_pixels_only_not_map_probability",
        "private_visual_review_candidates": reviewed,
        "map02_identified": False,
        "scene_transition_authenticated": False,
        "bizhawk_replay_authenticated": False,
        "real_ps1_input_to_display_offset_verified": False,
        "gpu_vram_frame_authenticated": False,
        "owner_private_data_uploaded": False,
    }


def save_private_report(report: dict, path: Path) -> None:
    destination = Path(path)
    if (not destination.is_absolute() or destination.is_symlink()
            or destination.exists() or destination.parent.is_symlink()
            or not destination.parent.is_dir()):
        raise ValueError("private report requires a new file in existing absolute directory")
    if any((parent / ".git").exists()
           for parent in (destination.parent, *destination.parents)):
        raise ValueError("private report must remain outside Git checkout")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(report, writer, sort_keys=True, indent=2)
            writer.write("\n")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    if not stat.S_ISREG(destination.stat().st_mode):
        raise ValueError("private review report must be regular")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_plan", type=Path)
    parser.add_argument("owner_private_capture_log", type=Path)
    parser.add_argument("owner_private_png_directory", type=Path)
    parser.add_argument("--private-report-output", type=Path, required=True)
    parser.add_argument("--pixel-change-threshold", type=int, default=32)
    parser.add_argument("--min-neutral-frames", type=int, default=180)
    parser.add_argument("--max-neutral-frames", type=int, default=1800)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=933949)
    a = parser.parse_args()
    try:
        result = triage(
            a.owner_private_bk2, a.owner_private_plan,
            a.owner_private_capture_log, a.owner_private_png_directory,
            minimum=a.min_neutral_frames, maximum=a.max_neutral_frames,
            after=a.after_input_frame, before=a.before_input_frame,
            pixel_threshold=a.pixel_change_threshold,
        )
        save_private_report(result, a.private_report_output)
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        parser.error("private visual comparison unavailable")
    changed = sum(1 for x in result["private_visual_review_candidates"]
                  if x["prominent_unmasked_pixel_difference"])
    print("VH_MAP02_PRIVATE_VISUAL_TRIAGE_READY groups=%d prominent_pixel_differences=%d map02_identified=0" %
          (len(result["private_visual_review_candidates"]), changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
