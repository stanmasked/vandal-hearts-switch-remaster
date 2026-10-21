#!/usr/bin/env python3
"""Owner-local BK2 chronological handoff: Start witness -> later scene candidates.

Accepts the *sanitized* result of PR #407's separate Start-capture validator,
then independently re-verifies both original private candidate datasets using
PR #409's decoded-RGBA comparison. This does not authenticate the sanitized
Start report, original PS1 game, real emulator execution, or MAP02 scene.
No network, no screenshot or private hash in result.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.validate_map02_private_replay_markers import _read_regular
from tools.compare_map02_private_replay_rasters import compare, _observations

START_SCHEMA = "vh.map02.private-start-anchor-replay-repeatability.v1"
HANDOFF_SCHEMA = "vh.map02.private-start-to-candidate-order.v1"
MOVIE_SCHEMA = "vh.psx.bizhawk.private-bk2-input-inspection.v1"
MOVIE_FRAMES = 933949
START_INPUT = 1661
START_LAST_COUNTER = 1663
MAX_REPORT_BYTES = 32768
EXPECTED_START = frozenset((
    "schema", "separate_capture_bundle_count",
    "capture_run_independence_authenticated",
    "matching_screenshot_counter_count", "first_start_input_index_zero_based",
    "capture_counters_one_based", "png_sha256_repeats_identically",
    "recorded_movie_start_input_matches_expected_anchor",
    "emulator_playback_executed_authenticated",
    "screen_pixel_provenance_verified",
    "input_to_displayed_image_offset_independently_verified",
    "map02_scene_frame_identified", "ps1_gpu_or_vram_verified",
    "owner_private_files_uploaded",
))


def read_json_private(path: Path) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("duplicate private report key")
            obj[key] = value
        return obj

    data = json.loads(_read_regular(path, MAX_REPORT_BYTES),
                      object_pairs_hook=unique)
    if not isinstance(data, dict):
        raise ValueError("expected private JSON object")
    return data


def validate_start_report(report: dict) -> None:
    if (frozenset(report) != EXPECTED_START or
            report.get("schema") != START_SCHEMA or
            type(report.get("separate_capture_bundle_count")) is not int or
            report["separate_capture_bundle_count"] != 2 or
            type(report.get("matching_screenshot_counter_count")) is not int or
            report["matching_screenshot_counter_count"] != 3 or
            type(report.get("first_start_input_index_zero_based")) is not int or
            report["first_start_input_index_zero_based"] != START_INPUT or
            report.get("capture_counters_one_based") != [1661, 1662, 1663] or
            report.get("png_sha256_repeats_identically") is not True or
            report.get("recorded_movie_start_input_matches_expected_anchor") is not True):
        raise ValueError("incompatible Start-anchor report")
    for key in (
        "capture_run_independence_authenticated",
        "emulator_playback_executed_authenticated",
        "screen_pixel_provenance_verified",
        "input_to_displayed_image_offset_independently_verified",
        "map02_scene_frame_identified", "ps1_gpu_or_vram_verified",
        "owner_private_files_uploaded",
    ):
        if report.get(key) is not False:
            raise ValueError("Start-anchor report overclaims authentication")


def verify(inspection: Path, start_report: Path,
           markers_one: Path, manifest_one: Path, images_one: Path,
           markers_two: Path, manifest_two: Path, images_two: Path) -> dict:
    original = read_json_private(inspection)
    if (original.get("schema") != MOVIE_SCHEMA or
            original.get("game") != "Vandal Hearts (USA)" or
            original.get("platform") != "PSX" or
            original.get("core") != "Octoshock" or
            type(original.get("input_log_frame_count")) is not int or
            original["input_log_frame_count"] != MOVIE_FRAMES or
            original.get("original_ps1_game_image_authenticated") is not False or
            original.get("map02_scene_frame_identified") is not False):
        raise ValueError("original movie inspection does not match Start anchor")
    if Path(start_report).resolve(strict=True) == Path(inspection).resolve(strict=True):
        raise ValueError("Start report and movie inspection must be separate")
    validate_start_report(read_json_private(start_report))

    candidate = compare(inspection, markers_one, manifest_one, images_one,
                        markers_two, manifest_two, images_two)
    if (candidate.get("decoded_rgba_rasters_equal") is not True or
            candidate.get("candidate_boundary_raster_change_observed") is not True or
            candidate.get("scene_transition_authenticated") is not False or
            candidate.get("map02_scene_frame_identified") is not False):
        raise ValueError("candidate comparison result incompatible")
    first = _observations(manifest_one)
    second = _observations(manifest_two)
    # The Start snapshot counters cannot also be claimed as a later
    # MAP02 scene candidate. The original BK2 report is only a frame range.
    # Require *every* candidate observation to be strictly later than 1663.
    if not first or len(first) != len(second):
        raise ValueError("candidate observation count differs")
    for a, b in zip(first, second):
        if (a["emulator_counter"] <= START_LAST_COUNTER or
                b["emulator_counter"] <= START_LAST_COUNTER or
                a["movie_input_candidate"] <= START_INPUT + 1 or
                b["movie_input_candidate"] <= START_INPUT + 1):
            raise ValueError("scene candidate overlaps or precedes Start anchor")
        if (a["movie_input_candidate"] >= MOVIE_FRAMES or
                b["movie_input_candidate"] >= MOVIE_FRAMES):
            raise ValueError("candidate input outside BK2 movie length")
    return {
        "schema": HANDOFF_SCHEMA,
        "movie_input_frame_count": MOVIE_FRAMES,
        "known_start_input_zero_based": START_INPUT,
        "later_candidate_observation_pairs": len(first),
        "all_candidate_observations_after_start_capture": True,
        "two_candidate_sets_revalidated": True,
        "decoded_raster_repeatable_and_visibly_changed": True,
        "start_anchor_sanitized_report_consistent": True,
        "start_png_bytes_reverified_by_this_tool": False,
        "original_ps1_disc_authenticated": False,
        "real_emulator_runs_authenticated": False,
        "input_to_video_timing_verified": False,
        "map02_scene_frame_identified": False,
        "gameplay_or_ps1_vram_parity_verified": False,
        "private_content_uploaded": False,
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
            args.second_markers, args.second_manifest, args.second_images)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        parser.error("private Start-to-candidate chronology not demonstrated")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
