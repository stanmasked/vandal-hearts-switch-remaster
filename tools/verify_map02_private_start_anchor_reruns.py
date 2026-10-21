#!/usr/bin/env python3
"""Compare two owner-private three-frame Start-anchor screenshot runs.

This is a byte-repeatability check of screenshots and self-reported movie
input labels. It does not authenticate a PS1 disc or actual rendered frame.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from tools.validate_map02_private_replay_markers import _read_regular
from tools.verify_map02_private_visual_candidates import (
    png_header_and_crc, read_png_private,
)
from tools.map02_private_png_idat import verify_idat_scanlines

SCHEMA = "vh.map02.private-start-anchor-replay-repeatability.v1"
FRAME_COUNT = 933949
SOURCE_SCHEMA = "vh.psx.bizhawk.private-bk2-input-inspection.v1"
RECORD = re.compile(
    r"^VH_PRIVATE_START_CAPTURE counter=([0-9]+) "
    r"candidate_input=([0-9]+) start_pressed=(yes|no) "
    r"mode=PLAY png=written$"
)
COMPLETE = (
    "VH_PRIVATE_START_CAPTURE_COMPLETE snapshots=3 "
    "movie_input_anchor_1661=yes displayed_frame_offset=unverified"
)
COUNTERS = (1661, 1662, 1663)
MAX_LOG_BYTES = 128 * 1024
MAX_INSPECTION = 32 * 1024


def inspect_report(inspection_path: Path) -> None:
    report = json.loads(_read_regular(inspection_path, MAX_INSPECTION))
    if (not isinstance(report, dict)
            or report.get("schema") != SOURCE_SCHEMA
            or report.get("game") != "Vandal Hearts (USA)"
            or report.get("platform") != "PSX"
            or report.get("core") != "Octoshock"
            or type(report.get("input_log_frame_count")) is not int
            or report["input_log_frame_count"] != FRAME_COUNT
            or report.get("map02_scene_frame_identified") is not False
            or report.get("original_ps1_game_image_authenticated") is not False):
        raise ValueError("invalid or unauthenticated private BK2 metadata")


def one_run(private_log: Path, screenshot_root: Path) -> list[bytes]:
    lines = _read_regular(private_log, MAX_LOG_BYTES).splitlines()
    entries = []
    complete = 0
    for line in lines:
        if line.startswith("VH_PRIVATE_START_CAPTURE_ERROR"):
            raise ValueError("owner-local screenshot probe reported an error")
        if line == COMPLETE:
            complete += 1
        elif line.startswith("VH_PRIVATE_START_CAPTURE"):
            match = RECORD.fullmatch(line)
            if match is None:
                raise ValueError("malformed capture record")
            counter, candidate, pressed = match.groups()
            index = len(entries)
            if (index >= 3 or int(counter) != COUNTERS[index]
                    or int(candidate) != COUNTERS[index] - 1
                    or (index == 0 and pressed != "no")
                    or (index == 1 and pressed != "yes")):
                raise ValueError("Start capture frame or movie input mismatch")
            entries.append((int(counter), pressed))
    if len(entries) != 3 or complete != 1 or lines.index(COMPLETE) < max(
            i for i, line in enumerate(lines) if RECORD.fullmatch(line)):
        raise ValueError("incomplete or out-of-order capture")
    hashes = []
    for counter in COUNTERS:
        filename = "vh_start_anchor_counter_%07d.png" % counter
        data = read_png_private(screenshot_root, filename)
        png_header_and_crc(data)
        verify_idat_scanlines(data)
        hashes.append(hashlib.sha256(data).digest())
    return hashes


def verify(private_inspection: Path, log_one: Path, folder_one: Path,
           log_two: Path, folder_two: Path) -> dict:
    inspect_report(private_inspection)
    # Paths must not be the same run, even when byte contents are equal.
    if Path(log_one).resolve() == Path(log_two).resolve() or Path(folder_one).resolve() == Path(folder_two).resolve():
        raise ValueError("repeatability comparison requires two distinct local runs")
    first = one_run(log_one, folder_one)
    second = one_run(log_two, folder_two)
    if first != second:
        raise ValueError("PNG capture bytes differ between two private runs")
    return {
        "schema": SCHEMA,
        "separate_capture_bundle_count": 2,
        "capture_run_independence_authenticated": False,
        "matching_screenshot_counter_count": 3,
        "first_start_input_index_zero_based": 1661,
        "capture_counters_one_based": list(COUNTERS),
        "png_sha256_repeats_identically": True,
        "recorded_movie_start_input_matches_expected_anchor": True,
        "emulator_playback_executed_authenticated": False,
        "screen_pixel_provenance_verified": False,
        "input_to_displayed_image_offset_independently_verified": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_or_vram_verified": False,
        "owner_private_files_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_inspection_json", type=Path)
    parser.add_argument("run_one_capture_log", type=Path)
    parser.add_argument("run_one_image_root", type=Path)
    parser.add_argument("run_two_capture_log", type=Path)
    parser.add_argument("run_two_image_root", type=Path)
    args = parser.parse_args()
    try:
        result = verify(
            args.private_inspection_json,
            args.run_one_capture_log, args.run_one_image_root,
            args.run_two_capture_log, args.run_two_image_root,
        )
    except (OSError, ValueError, TypeError, UnicodeError, KeyError):
        parser.error("owner-private Start-anchor repeatability validation unavailable")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
