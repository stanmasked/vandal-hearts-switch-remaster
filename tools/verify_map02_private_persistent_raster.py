#!/usr/bin/env python3
"""Owner-local, stricter *raster-only* MAP02 candidate persistence witness.

Parent PR #413 already checks Start chronology, two private replay records,
individual PNG validity, decoded equality and a nonstatic candidate frame.
This optional gate asks for a subsequent post candidate screenshot and tests
whether a distributed image change persists in BOTH candidate and post
relative to the most recent pre frame.

A cursor, OSD, dialogue, fade or unrelated animation may still pass: the
tool NEVER authenticates a MAP02 scene or a real BizHawk/PS1 execution.
"""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path
import warnings

from PIL import Image, ImageChops, UnidentifiedImageError

from tools.verify_map02_private_start_candidate_order import verify as verify_parent
from tools.compare_map02_private_replay_rasters import _observations
from tools.verify_map02_private_visual_candidates import read_png_private

SCHEMA = "vh.map02.private-persistent-raster-witness.v1"
GRID = 4
MIN_TILES = 4
MIN_PIXELS = 16
FRACTION_DENOMINATOR = 100  # At least 1% persistent changed pixels
MAX_POST_COUNTER_GAP = 120


def _read_rgba(root: Path, shot: dict) -> Image.Image:
    raw = read_png_private(root, shot["png_file"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(BytesIO(raw)) as image:
            image.load()
            if (image.format != "PNG" or not 1 <= image.width <= 8192
                    or not 1 <= image.height <= 8192
                    or image.width * image.height > 20_000_000):
                raise ValueError("unsupported private PNG dimensions")
            return image.convert("RGBA")


def _changed(before: Image.Image, after: Image.Image) -> Image.Image:
    if before.size != after.size:
        raise ValueError("captured raster dimensions changed between frames")
    channels = ImageChops.difference(before, after).split()
    mask = channels[0]
    for channel in channels[1:]:
        mask = ImageChops.lighter(mask, channel)
    return mask.point(lambda channel: 255 if channel else 0)


def _covered_tiles(mask: Image.Image) -> int:
    width, height = mask.size
    hit = 0
    for row in range(GRID):
        for col in range(GRID):
            tile = (
                col * width // GRID, row * height // GRID,
                (col + 1) * width // GRID, (row + 1) * height // GRID,
            )
            if tile[0] < tile[2] and tile[1] < tile[3]:
                hit += mask.crop(tile).getbbox() is not None
    return hit


def persistent_witness(pre: Image.Image, candidate: Image.Image,
                       post: Image.Image) -> None:
    if (pre.mode != "RGBA" or candidate.mode != "RGBA"
            or post.mode != "RGBA" or pre.size != candidate.size
            or pre.size != post.size):
        raise ValueError("raster mode or dimensions incompatible")
    width, height = pre.size
    # Not suitable for tiny/icon-only captures.
    if width < 16 or height < 16:
        raise ValueError("raster too small for distributed-change witness")
    threshold = max(
        MIN_PIXELS, (width * height + FRACTION_DENOMINATOR - 1)
        // FRACTION_DENOMINATOR,
    )
    first = _changed(pre, candidate)
    later = _changed(pre, post)
    shared = ImageChops.darker(first, later)
    if shared.histogram()[255] < threshold:
        raise ValueError("insufficient persistent changed pixels")
    if _covered_tiles(shared) < MIN_TILES:
        raise ValueError("persistent change too spatially localized")


def select_window(frames: list[dict]) -> tuple[dict, dict, dict]:
    pre = None
    candidate = None
    post = None
    for shot in frames:
        if shot["label"] == "pre_map02" and candidate is None:
            pre = shot
        elif shot["label"] == "map02_candidate" and candidate is None:
            candidate = shot
        elif shot["label"] == "post_map02" and candidate is not None:
            post = shot
            break
    if pre is None or candidate is None or post is None:
        raise ValueError("pre, candidate and post observations required")
    gap = post["emulator_counter"] - candidate["emulator_counter"]
    if not 0 < gap <= MAX_POST_COUNTER_GAP:
        raise ValueError("post observation too remote from candidate")
    return pre, candidate, post


def verify(
    inspection: Path, start_report: Path,
    markers_one: Path, manifest_one: Path, images_one: Path,
    markers_two: Path, manifest_two: Path, images_two: Path,
) -> dict:
    previous = verify_parent(
        inspection, start_report, markers_one, manifest_one, images_one,
        markers_two, manifest_two, images_two,
    )
    if previous["map02_scene_frame_identified"] is not False:
        raise ValueError("parent report overclaims scene authentication")
    frames_one = _observations(manifest_one)
    frames_two = _observations(manifest_two)
    first = select_window(frames_one)
    second = select_window(frames_two)
    if [(f["emulator_counter"], f["label"]) for f in first] != [
            (f["emulator_counter"], f["label"]) for f in second]:
        raise ValueError("selected candidate windows differ between runs")
    # Parent already validated equality of the complete decoded screenshots
    # between runs. Repeating the stricter spatial check on BOTH paths
    # ensures the verdict is not based on a copied or stale single root.
    for root, window in ((images_one, first), (images_two, second)):
        rgba = [_read_rgba(root, shot) for shot in window]
        persistent_witness(*rgba)
    return {
        "schema": SCHEMA,
        "separately_supplied_capture_sets_revalidated": True,
        "known_start_anchor_precedes_candidate": True,
        "same_input_frame_candidate_and_post_labels": True,
        "post_capture_within_120_counters": True,
        "decoded_raster_persistent_change_at_least_one_percent": True,
        "persistently_changed_pixels_span_at_least_four_4x4_tiles": True,
        "two_supplied_raster_windows_pass": True,
        "original_ps1_game_authenticated": False,
        "real_independent_emulator_runs_authenticated": False,
        "input_to_displayed_frame_offset_authenticated": False,
        "actual_map02_scene_transition_authenticated": False,
        "gameplay_or_gpu_vram_parity_authenticated": False,
        "private_png_logs_or_hashes_uploaded": False,
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
        report = verify(
            args.inspection_json, args.start_anchor_report_json,
            args.first_markers, args.first_manifest, args.first_images,
            args.second_markers, args.second_manifest, args.second_images,
        )
    except (OSError, ValueError, TypeError, KeyError, UnidentifiedImageError):
        parser.error("persistent private candidate raster witness not demonstrated")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
