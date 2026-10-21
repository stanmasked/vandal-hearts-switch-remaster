#!/usr/bin/env python3
"""Owner-private BK2 three-prehistory-frame change witness.

Builds on PR #425's two-pre animation mask: a pixel contributes only when
its entire RGBA value agrees in THREE supplied pre-candidate images, changes
at the candidate, and keeps exactly the same new value in the post image.
This counters some aliased animation patterns; does NOT identify MAP02.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import ImageChops, UnidentifiedImageError

from tools.verify_map02_private_animation_baseline import (
    verify as verify_parent, _changed, _covered_tiles, _read_rgba,
    MIN_PIXELS, MIN_TILES, FRACTION_DENOMINATOR,
    MAX_PRE_COUNTER_GAP, MAX_PRE_TO_CANDIDATE_GAP,
    MAX_POST_COUNTER_GAP,
)
from tools.compare_map02_private_replay_rasters import _observations

SCHEMA = "vh.map02.private-three-prehistory-witness.v1"
MIN_PRE_IMAGES = 3


def select_five_frame_window(shots: list[dict]) -> tuple[dict, dict, dict, dict, dict]:
    pre = []
    candidate = None
    post = None
    for shot in shots:
        if shot["label"] == "pre_map02" and candidate is None:
            pre.append(shot)
        elif shot["label"] == "map02_candidate" and candidate is None:
            candidate = shot
        elif shot["label"] == "post_map02" and candidate is not None:
            post = shot
            break
    if len(pre) < MIN_PRE_IMAGES or candidate is None or post is None:
        raise ValueError("three pre, candidate and post observations required")
    selected = (*pre[-MIN_PRE_IMAGES:], candidate, post)
    counters = [s["emulator_counter"] for s in selected]
    if (any(type(x) is not int for x in counters)
            or any(b <= a for a, b in zip(counters, counters[1:]))):
        raise ValueError("three-pre frame counters out of sequence")
    allowed = [MAX_PRE_COUNTER_GAP] * (MIN_PRE_IMAGES - 1) + [
        MAX_PRE_TO_CANDIDATE_GAP, MAX_POST_COUNTER_GAP,
    ]
    if any(b - a > gap for a, b, gap in
           zip(counters, counters[1:], allowed)):
        raise ValueError("prehistory/candidate/post samples too far apart")
    return selected


def check_three_pre_history(first, middle, recent, candidate, post) -> None:
    images = (first, middle, recent, candidate, post)
    if (any(image.mode != "RGBA" for image in images)
            or any(image.size != recent.size for image in images)):
        raise ValueError("three-pre raster mode or dimensions incompatible")
    width, height = recent.size
    if width < 16 or height < 16:
        raise ValueError("three-pre raster too small")
    threshold = max(
        MIN_PIXELS,
        (width * height + FRACTION_DENOMINATOR - 1) // FRACTION_DENOMINATOR,
    )
    # Comparing only the LAST TWO pre snapshots falsely admits e.g.
    # animated background B->A->A. This gate excludes any position where
    # either earlier sampled RGBA pixel differs from the last pre image.
    first_equal = ImageChops.invert(_changed(first, recent))
    middle_equal = ImageChops.invert(_changed(middle, recent))
    new_at_candidate = _changed(recent, candidate)
    same_candidate_post = ImageChops.invert(_changed(candidate, post))
    qualified = ImageChops.darker(
        ImageChops.darker(first_equal, middle_equal),
        ImageChops.darker(new_at_candidate, same_candidate_post),
    )
    if qualified.histogram()[255] < threshold:
        raise ValueError("insufficient new stable pixels outside three-pre animation history")
    if _covered_tiles(qualified) < MIN_TILES:
        raise ValueError("three-pre stable pixels too spatially localized")


def verify(
    inspection: Path, start_report: Path,
    markers_one: Path, manifest_one: Path, images_one: Path,
    markers_two: Path, manifest_two: Path, images_two: Path,
) -> dict:
    parent = verify_parent(
        inspection, start_report, markers_one, manifest_one, images_one,
        markers_two, manifest_two, images_two,
    )
    if (parent.get("map02_scene_start_authenticated") is not False
            or parent.get("pre_existing_animation_pixels_excluded") is not True):
        raise ValueError("prior two-pre evidence is inconsistent")
    selections = [
        select_five_frame_window(_observations(manifest_one)),
        select_five_frame_window(_observations(manifest_two)),
    ]
    if ([(s["emulator_counter"], s["movie_input_candidate"], s["label"])
         for s in selections[0]] !=
            [(s["emulator_counter"], s["movie_input_candidate"], s["label"])
             for s in selections[1]]):
        raise ValueError("three-pre replay windows disagree")
    # Parent rechecks full private manifests, PNG SHA/CRC/IDAT and paired
    # decoded rasters. Repeat strict five-image check independently on both
    # supplied directories; neither proves separate real emulator processes.
    for root, window in (
        (images_one, selections[0]), (images_two, selections[1])
    ):
        check_three_pre_history(*[_read_rgba(root, shot) for shot in window])
    return {
        "schema": SCHEMA,
        "owner_supplied_pre_frame_samples": MIN_PRE_IMAGES,
        "two_supplied_five_frame_windows_checked": True,
        "three_pre_rgba_samples_stable_for_counted_pixels": True,
        "new_candidate_values_equal_post_rgba": True,
        "new_stable_pixels_at_least_one_percent_and_four_tiles": True,
        "consecutive_pre_and_candidate_gaps_at_most_120": True,
        "previous_start_and_png_checks_passed": True,
        "original_ps1_game_authenticated": False,
        "separate_real_emulator_processes_authenticated": False,
        "input_to_video_offset_authenticated": False,
        "actual_map02_scene_authenticated": False,
        "ps1_gpu_vram_parity_authenticated": False,
        "private_data_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspection_json", type=Path)
    parser.add_argument("start_anchor_report_json", type=Path)
    parser.add_argument("--first-markers", required=True, type=Path)
    parser.add_argument("--first-manifest", required=True, type=Path)
    parser.add_argument("--first-images", required=True, type=Path)
    parser.add_argument("--second-markers", required=True, type=Path)
    parser.add_argument("--second-manifest", required=True, type=Path)
    parser.add_argument("--second-images", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            args.inspection_json, args.start_anchor_report_json,
            args.first_markers, args.first_manifest, args.first_images,
            args.second_markers, args.second_manifest, args.second_images,
        )
    except (ValueError, TypeError, KeyError, OSError, UnidentifiedImageError):
        parser.error("three-frame prehistory raster witness not demonstrated")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
