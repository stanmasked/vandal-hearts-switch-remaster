#!/usr/bin/env python3
"""Owner-private BK2 animation-baseline filter; no authentic PS1 scene claim.

Two *pre*-candidate frames identify pixels already changing before the
proposed boundary. Only pixels that are unchanged between those pre frames,
then switch to an identical candidate/post RGBA value, count as new, stable
visual change. This supplements (never replaces) all earlier checks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import json

from PIL import ImageChops, UnidentifiedImageError

from tools.verify_map02_private_persistent_raster import (
    _read_rgba, _changed, _covered_tiles, verify as verify_parent,
    GRID, MIN_TILES, MIN_PIXELS, FRACTION_DENOMINATOR,
    MAX_POST_COUNTER_GAP,
)
from tools.compare_map02_private_replay_rasters import _observations

SCHEMA = "vh.map02.private-animation-baseline-witness.v1"
MAX_PRE_COUNTER_GAP = 120
MAX_PRE_TO_CANDIDATE_GAP = 120


def select_animation_window(shots: list[dict]) -> tuple[dict, dict, dict, dict]:
    """Select last TWO pre samples, first candidate, earliest following post."""
    pre = []
    candidate = None
    post = None
    for shot in shots:
        label = shot["label"]
        if label == "pre_map02" and candidate is None:
            pre.append(shot)
        elif label == "map02_candidate" and candidate is None:
            candidate = shot
        elif label == "post_map02" and candidate is not None:
            post = shot
            break
    if len(pre) < 2 or candidate is None or post is None:
        raise ValueError("two pre, candidate and post observations required")
    older, recent = pre[-2:]
    times = [s["emulator_counter"] for s in (older, recent, candidate, post)]
    if (any(type(t) is not int for t in times)
            or any(right <= left for left, right in zip(times, times[1:]))):
        raise ValueError("animation-baseline counters not strictly increasing")
    if times[1] - times[0] > MAX_PRE_COUNTER_GAP:
        raise ValueError("pre-animation baseline samples too remote")
    if times[2] - times[1] > MAX_PRE_TO_CANDIDATE_GAP:
        raise ValueError("candidate too remote from recent pre-baseline")
    if times[3] - times[2] > MAX_POST_COUNTER_GAP:
        raise ValueError("post-candidate witness too remote")
    return older, recent, candidate, post


def check_animated_background(older, recent, candidate, post) -> None:
    images = (older, recent, candidate, post)
    if (any(im.mode != "RGBA" for im in images)
            or any(im.size != recent.size for im in images)):
        raise ValueError("animation-baseline RGBA dimensions incompatible")
    width, height = recent.size
    if width < 16 or height < 16:
        raise ValueError("animation-baseline screenshots too small")

    # Only positions that have the SAME full RGBA pixel value in both
    # pre-candidate frames are eligible to become "newly stable" pixels.
    stationary_pre = ImageChops.invert(_changed(older, recent))
    newly_changed = _changed(recent, candidate)
    stable_after = ImageChops.invert(_changed(candidate, post))
    eligible = ImageChops.darker(
        ImageChops.darker(stationary_pre, newly_changed), stable_after)
    minimum = max(
        MIN_PIXELS, (width * height + FRACTION_DENOMINATOR - 1)
        // FRACTION_DENOMINATOR,
    )
    if eligible.histogram()[255] < minimum:
        raise ValueError("insufficient newly stable pixels outside prior animation")
    if _covered_tiles(eligible) < MIN_TILES:
        raise ValueError("newly stable pixels confined to too few screen tiles")


def verify(
    inspection: Path, start_report: Path,
    markers_one: Path, manifest_one: Path, images_one: Path,
    markers_two: Path, manifest_two: Path, images_two: Path,
) -> dict:
    previous = verify_parent(
        inspection, start_report, markers_one, manifest_one, images_one,
        markers_two, manifest_two, images_two,
    )
    if (previous.get("actual_map02_scene_transition_authenticated") is not False
            or previous.get("persistent_candidate_post_rgba_values_identical") is not True):
        raise ValueError("upstream private proof incompatible")

    windows = [
        select_animation_window(_observations(manifest_one)),
        select_animation_window(_observations(manifest_two)),
    ]
    if [[(s["emulator_counter"], s["movie_input_candidate"], s["label"])
         for s in window] for window in windows][0] != [
             (s["emulator_counter"], s["movie_input_candidate"], s["label"])
             for s in windows[1]]:
        raise ValueError("replays disagree on animation-baseline frame indices")
    for root, shots in ((images_one, windows[0]), (images_two, windows[1])):
        check_animated_background(*[_read_rgba(root, s) for s in shots])

    return {
        "schema": SCHEMA,
        "two_separate_supplied_capture_sets_revalidated": True,
        "two_pre_candidate_frames_checked_per_run": True,
        "pre_existing_animation_pixels_excluded": True,
        "new_changed_pixels_stable_into_post": True,
        "new_stable_change_at_least_one_percent_and_four_tiles": True,
        "pre_baseline_and_post_intervals_within_120_counters": True,
        "candidate_temporal_and_rgba_repeatability_checked": True,
        "original_ps1_game_authenticated": False,
        "two_real_emulator_processes_authenticated": False,
        "movie_to_video_offset_authenticated": False,
        "map02_scene_start_authenticated": False,
        "ps1_gpu_vram_parity_authenticated": False,
        "owner_private_files_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inspection_json", type=Path)
    parser.add_argument("start_anchor_report_json", type=Path)
    parser.add_argument("--first-markers", type=Path, required=True)
    parser.add_argument("--first-manifest", type=Path, required=True)
    parser.add_argument("--first-images", type=Path, required=True)
    parser.add_argument("--second-markers", type=Path, required=True)
    parser.add_argument("--second-manifest", type=Path, required=True)
    parser.add_argument("--second-images", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(
            args.inspection_json, args.start_anchor_report_json,
            args.first_markers, args.first_manifest, args.first_images,
            args.second_markers, args.second_manifest, args.second_images,
        )
    except (ValueError, TypeError, KeyError, OSError, UnidentifiedImageError):
        parser.error("pre-existing animation excluded visual witness not demonstrated")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
