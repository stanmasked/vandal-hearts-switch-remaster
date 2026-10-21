#!/usr/bin/env python3
"""Cross-check three owner-private screenshot markers against BK2 source CSV.

This checks recorded MOVIE input, NOT actual PS1 controller delivery,
screenshot presentation timing, image identity or MAP02.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from tools.inspect_map02_private_bk2 import BUTTONS
from tools.validate_map02_private_replay_markers import _read_regular
from tools.verify_map02_private_bk2_input_handshake import (
    inspect_reference, read_private, MAX_CSV_BYTES,
)
from tools.verify_map02_private_start_anchor_reruns import (
    RECORD, MAX_LOG_BYTES, COUNTERS,
    verify as verify_two_capture_bundles,
)

SCHEMA = "vh.map02.private-start-anchor-bk2-csv-crosscheck.v1"
MAX_INSPECTION = 32768
ANCHOR = (1660, 1661, 1662)
START_MASK = 1 << BUTTONS.index("Start")


def expected_states(inspection_path: Path, events_csv_path: Path) -> tuple[bool, bool, bool]:
    """Use exported BK2 press/release history, NOT guessed Start release timing."""
    report_text = read_private(inspection_path, MAX_INSPECTION)
    report = json.loads(report_text)
    if (not isinstance(report, dict)
            or report.get("input_log_frame_count") != 933949
            or type(report.get("input_log_frame_count")) is not int):
        raise ValueError("wrong owner BK2 frame-count fingerprint")
    csv_text = read_private(events_csv_path, MAX_CSV_BYTES)
    start, length, masks, _ = inspect_reference(report_text, csv_text)
    if not (start <= ANCHOR[0] and start + length > ANCHOR[2]):
        raise ValueError("exported source CSV does not span all three Start frames")
    states = tuple(bool(masks[frame - start] & START_MASK) for frame in ANCHOR)
    if states[0] or not states[1]:
        raise ValueError("first Start press is inconsistent with the source export")
    return states


def recorded_states(log_path: Path) -> tuple[bool, bool, bool]:
    states = []
    for line in _read_regular(log_path, MAX_LOG_BYTES).splitlines():
        if not line.startswith("VH_PRIVATE_START_CAPTURE"):
            continue
        m = RECORD.fullmatch(line)
        if m is None:
            # Only one exact summary marker is exempt; other records must
            # already have been rejected by the underlying verifier.
            if line.startswith("VH_PRIVATE_START_CAPTURE_COMPLETE"):
                continue
            raise ValueError("invalid private Start marker")
        counter, frame, state = m.groups()
        idx = len(states)
        if idx >= len(ANCHOR) or int(counter) != COUNTERS[idx] or int(frame) != ANCHOR[idx]:
            raise ValueError("Start movie index shifted or duplicated")
        states.append(state == "yes")
    if len(states) != 3:
        raise ValueError("incomplete recorded Start input states")
    return tuple(states)


def verify(inspection: Path, source_csv: Path,
           log_one: Path, folder_one: Path, log_two: Path, folder_two: Path) -> dict:
    # Check existing PNG envelope/IDAT decoding/hash equality, file safety,
    # exact counters, per-run Start onset and log completion first.
    underlying = verify_two_capture_bundles(
        inspection, log_one, folder_one, log_two, folder_two
    )
    source_states = expected_states(inspection, source_csv)
    first = recorded_states(log_one)
    second = recorded_states(log_two)
    if first != source_states or second != source_states:
        raise ValueError("private Lua movie-input labels differ from BK2 CSV")
    return {
        "schema": SCHEMA,
        "separate_capture_bundle_count": underlying["separate_capture_bundle_count"],
        "capture_counters_one_based": list(COUNTERS),
        "first_start_input_index_zero_based": 1661,
        "all_three_recorded_start_states_agree_with_private_bk2_csv": True,
        "third_frame_start_release_assumed": False,
        "both_capture_png_sets_byte_identical": True,
        "owner_bk2_read_or_authenticated_by_this_script": False,
        "two_real_emulator_runs_authenticated": False,
        "ps1_controller_input_delivery_verified": False,
        "input_to_displayed_image_offset_verified": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_or_vram_verified": False,
        "private_source_data_uploaded": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_inspection_json", type=Path)
    p.add_argument("private_bk2_events_csv", type=Path)
    p.add_argument("run_one_capture_log", type=Path)
    p.add_argument("run_one_image_root", type=Path)
    p.add_argument("run_two_capture_log", type=Path)
    p.add_argument("run_two_image_root", type=Path)
    a = p.parse_args()
    try:
        summary = verify(
            a.private_inspection_json, a.private_bk2_events_csv,
            a.run_one_capture_log, a.run_one_image_root,
            a.run_two_capture_log, a.run_two_image_root,
        )
    except (OSError, ValueError, TypeError, UnicodeError, KeyError,
            csv.Error):
        p.error("private BK2-to-screenshot anchor audit unavailable")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
