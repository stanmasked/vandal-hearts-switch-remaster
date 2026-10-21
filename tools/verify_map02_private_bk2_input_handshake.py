#!/usr/bin/env python3
"""Owner-local verification of a bounded BizHawk movie-input handshake.

A match proves agreement of TWO views of the movie's controller stream,
not emulator input execution, authentic gameplay, or MAP02 GPU/VRAM.
Never uploads movie input/CSV or prints private paths.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path
import re
import stat

from tools.inspect_map02_private_bk2 import BUTTONS

SCHEMA = "vh.map02.private-bk2-input-handshake.v1"
INSPECTION = "vh.psx.bizhawk.private-bk2-input-inspection.v1"
CSV_COLUMNS = (
    "frame_zero_based", "buttons_pressed", "buttons_released", "held_buttons"
)
RECORD = re.compile(
    r"^VH_PRIVATE_BK2_SYNC counter=([0-9]+) "
    r"candidate_input=([0-9]+) mask=([0-9]+) mode=PLAY$"
)
MAX_CSV_BYTES = 4 * 1024 * 1024
MAX_LOG_BYTES = 1024 * 1024
MAX_JSON_BYTES = 32768
MAX_WINDOW = 24000
BUTTON_INDEX = {name: index for index, name in enumerate(BUTTONS)}


def read_private(path: Path, limit: int) -> str:
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("private input must be regular and not symlinked")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("private input exceeds size bound")
    with path.open("rb") as f:
        data = f.read(limit + 1)
    if len(data) > limit:
        raise ValueError("private input exceeds size bound")
    return data.decode("utf-8")


def split_buttons(value: str) -> frozenset[str]:
    if not value:
        return frozenset()
    items = value.split("+")
    if len(items) != len(set(items)) or any(x not in BUTTON_INDEX for x in items):
        raise ValueError("invalid controller button name or duplicate")
    return frozenset(items)


def mask_of(buttons: frozenset[str]) -> int:
    return sum(1 << BUTTON_INDEX[name] for name in buttons)


def inspect_reference(report_text: str, csv_text: str) -> tuple[int, int, list[int], int]:
    report = json.loads(report_text)
    if not isinstance(report, dict) or report.get("schema") != INSPECTION:
        raise ValueError("wrong BK2 inspection format")
    if (report.get("platform") != "PSX" or report.get("core") != "Octoshock"
            or report.get("game") != "Vandal Hearts (USA)"
            or report.get("map02_scene_frame_identified") is not False
            or report.get("original_ps1_game_image_authenticated") is not False):
        raise ValueError("incorrect controller input provenance")
    count = report.get("input_log_frame_count")
    window = report.get("window")
    if type(count) is not int or not 1 <= count <= 1_500_000 or not isinstance(window, dict):
        raise ValueError("invalid source frame count or window")
    start, length, expected_changes = (
        window.get("start_frame"), window.get("length_requested"),
        window.get("changes_exported")
    )
    if any(type(v) is not int for v in (start, length, expected_changes)):
        raise ValueError("missing integer window fields")
    if (start < 0 or not 1 <= length <= MAX_WINDOW
            or start + length > count
            or not 1 <= expected_changes <= length):
        raise ValueError("source window outside BK2")
    stream = csv.DictReader(io.StringIO(csv_text, newline=""))
    if tuple(stream.fieldnames or ()) != CSV_COLUMNS:
        raise ValueError("CSV controller schema differs")
    changes: list[tuple[int, frozenset[str]]] = []
    last_frame = start - 1
    prior = None
    start_onsets = 0
    start_onset_frames = []
    for row in stream:
        if len(changes) >= MAX_WINDOW or None in row or None in row.values():
            raise ValueError("too many/invalid controller changes")
        raw_frame = row["frame_zero_based"]
        if not raw_frame.isascii() or not raw_frame.isdecimal():
            raise ValueError("bad source controller frame")
        frame = int(raw_frame)
        if not last_frame < frame < start + length:
            raise ValueError("controller frame order or range invalid")
        if not changes and frame != start:
            raise ValueError("source window lacks first baseline")
        pressed = split_buttons(row["buttons_pressed"])
        released = split_buttons(row["buttons_released"])
        held = split_buttons(row["held_buttons"])
        if pressed & released:
            raise ValueError("same button simultaneously pressed and released")
        if prior is not None:
            if pressed != held - prior or released != prior - held:
                raise ValueError("input edge does not agree with held state")
            if not (pressed or released):
                raise ValueError("redundant controller change row")
        if "Start" in pressed:
            start_onsets += 1
            start_onset_frames.append(frame)
        changes.append((frame, held))
        prior = held
        last_frame = frame
    if len(changes) != expected_changes:
        raise ValueError("CSV does not match inspection changes count")
    # The known first Start onset for this owner recording is zero-based 1661.
    # Require the expected event whenever the selected window includes it.
    if start <= 1661 < start + length and 1661 not in start_onset_frames:
        raise ValueError("first owner Start anchor absent from bounded window")
    index = 0
    held = frozenset()
    masks: list[int] = []
    for frame in range(start, start + length):
        if index < len(changes) and changes[index][0] == frame:
            held = changes[index][1]
            index += 1
        masks.append(mask_of(held))
    if index != len(changes):
        raise ValueError("unprocessed input changes")
    return start, length, masks, start_onsets


def verify(inspection_json: Path, events_csv: Path, console_log: Path) -> dict:
    start, length, expected, onsets = inspect_reference(
        read_private(inspection_json, MAX_JSON_BYTES),
        read_private(events_csv, MAX_CSV_BYTES),
    )
    lines = read_private(console_log, MAX_LOG_BYTES).splitlines()
    actual: list[int] = []
    for line in lines:
        if line.startswith("VH_PRIVATE_BK2_SYNC_ERROR"):
            raise ValueError("BizHawk reported an incomplete input probe")
        if not line.startswith("VH_PRIVATE_BK2_SYNC"):
            continue  # unrelated private console text is never repeated
        match = RECORD.fullmatch(line)
        if match is None:
            raise ValueError("malformed BizHawk input probe")
        counter, candidate, mask = (int(v) for v in match.groups())
        n = len(actual)
        if (n >= length or counter != start + n + 1
                or candidate != start + n or mask >= (1 << len(BUTTONS))
                or mask != expected[n]):
            raise ValueError("input frame counter or movie button mask mismatch")
        actual.append(mask)
    if len(actual) != length:
        raise ValueError("incomplete BizHawk movie input probe")
    return {
        "schema": SCHEMA,
        "window_start_zero_based": start,
        "frames_compared": length,
        "all_movie_input_masks_match": True,
        "start_button_press_onsets_in_reference_window": onsets,
        "reported_movie_getinput_records_matched": True,
        "actual_lua_runtime_execution_verified": False,
        "original_game_boot_confirmed": False,
        "actual_emulated_input_delivery_verified": False,
        "emulator_to_bk2_frame_offset_independently_verified": False,
        "map02_scene_frame_identified": False,
        "ps1_gpu_or_vram_verified": False,
        "private_owner_data_uploaded": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_inspection_json", type=Path)
    p.add_argument("private_events_csv", type=Path)
    p.add_argument("private_bizhawk_console_log", type=Path)
    args = p.parse_args()
    try:
        result = verify(args.private_inspection_json, args.private_events_csv,
                        args.private_bizhawk_console_log)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, csv.Error):
        p.error("owner-private BK2 handshake not validated")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
