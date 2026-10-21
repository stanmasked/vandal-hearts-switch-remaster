#!/usr/bin/env python3
"""Recompute a private Start anchor DIRECTLY from the owner's BK2 archive.

No CSV, manually supplied inspection JSON or manifest can override the source
movie's recorded Start states. NEVER call this from public CI with owner data.
Even a match is not proof of real PS1 emulation or a MAP02 scene.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import stat
import zipfile

from tools.inspect_map02_private_bk2 import (
    MAX_FRAMES, MAX_INPUT_BYTES, MAX_FRAME_LENGTH, parse_header,
    parse_sync, read_small, safe_members, check_logkey, read_frame,
)
from tools.verify_map02_private_start_anchor_reruns import one_run
from tools.verify_map02_private_start_anchor_against_bk2_csv import recorded_states

SCHEMA = "vh.map02.direct-private-bk2-start-anchor.v1"
EXPECTED_FRAMES = 933949
EXPECTED_CHANGES = 20152
EXPECTED_PRESSES = 13150
EXPECTED_FIRST_START = 1661
ANCHOR = (1660, 1661, 1662)
CAPTURE_COUNTERS = (1661, 1662, 1663)
MAX_BK2_ARCHIVE = 8 * 1024 * 1024


def source_anchor(private_movie: Path) -> tuple[bool, bool, bool]:
    """Read and CRC-check the entire bounded Octoshock BK2, without export.

    The aggregate counts are a fingerprint of this owner's previously
    inspected movie, not an authentication of game contents or disc.
    """
    movie = Path(private_movie)
    if movie.is_symlink() or not movie.is_file():
        raise ValueError("requires regular non-symlinked local BK2")
    info = movie.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BK2_ARCHIVE:
        raise ValueError("BK2 archive size exceeds privacy boundary")

    with zipfile.ZipFile(movie) as archive:
        safe_members(archive)
        parse_header(read_small(archive, "Header.txt"))
        parse_sync(read_small(archive, "SyncSettings.json"))
        with archive.open("Input Log.txt") as src:
            if src.readline().strip() != b"[Input]":
                raise ValueError("BK2 input section missing")
            check_logkey(src.readline())
            count = 0
            input_bytes = 0
            changed_frames = 0
            press_onsets = 0
            analog_frames = 0
            first_start = None
            previous = frozenset()
            states = []
            ended = False
            for raw in src:
                input_bytes += len(raw)
                if input_bytes > MAX_INPUT_BYTES or len(raw) > MAX_FRAME_LENGTH + 2:
                    raise ValueError("bounded BK2 input size exceeded")
                line = raw.rstrip(b"\r\n")
                if line == b"[/Input]":
                    ended = True
                    break
                axes, buttons = read_frame(line)
                if count >= MAX_FRAMES:
                    raise ValueError("BK2 frame limit exceeded")
                if count in ANCHOR:
                    states.append("Start" in buttons)
                if buttons != previous:
                    changed_frames += 1
                    new_press = buttons - previous
                    press_onsets += len(new_press)
                    if first_start is None and "Start" in new_press:
                        first_start = count
                if axes != (128, 128, 128, 128):
                    analog_frames += 1
                previous = buttons
                count += 1
            if not ended or src.read(1):
                raise ValueError("BK2 missing end marker or has extra data")
    if (count != EXPECTED_FRAMES
            or changed_frames != EXPECTED_CHANGES
            or press_onsets != EXPECTED_PRESSES
            or analog_frames != 0
            or first_start != EXPECTED_FIRST_START
            or len(states) != len(ANCHOR)
            or states[0] or not states[1]):
        raise ValueError("source BK2 movie fingerprint or first Start mismatch")
    return tuple(states)


def verify(private_bk2: Path, run_one_log: Path, run_one_dir: Path,
           run_two_log: Path, run_two_dir: Path) -> dict:
    # Paths alone do not authenticate independence, but distinct paths are
    # a minimum and prevent accidentally comparing a run with itself.
    if (Path(run_one_log).resolve() == Path(run_two_log).resolve()
            or Path(run_one_dir).resolve() == Path(run_two_dir).resolve()):
        raise ValueError("requires distinct local capture bundles")
    if (Path(run_one_log).exists() and Path(run_two_log).exists()
            and Path(run_one_log).samefile(run_two_log)):
        raise ValueError("both log paths refer to the same file")

    truth = source_anchor(private_bk2)
    images_one = one_run(run_one_log, run_one_dir)
    images_two = one_run(run_two_log, run_two_dir)
    first = recorded_states(run_one_log)
    second = recorded_states(run_two_log)
    if first != truth or second != truth:
        raise ValueError("capture console Start values disagree with BK2")
    if images_one != images_two:
        raise ValueError("two private PNG capture sets differ")

    return {
        "schema": SCHEMA,
        "bk2_input_stream_read_directly_and_crc_checked": True,
        "bk2_frame_and_button_event_aggregate_matches_known_movie": True,
        "bk2_first_start_input_index_zero_based": EXPECTED_FIRST_START,
        "recorded_capture_counters_one_based": list(CAPTURE_COUNTERS),
        "all_three_start_states_match_direct_bk2_input": True,
        "separate_supplied_capture_bundle_count": 2,
        "png_bytes_match_between_supplied_bundles": True,
        "original_disc_or_firmware_authenticated": False,
        "genuine_emulator_execution_authenticated": False,
        "independent_real_replays_authenticated": False,
        "actual_ps1_controller_input_delivery_verified": False,
        "input_to_displayed_image_offset_verified": False,
        "map02_scene_frame_identified": False,
        "native_source_gpu_vram_verified": False,
        "private_movie_or_images_uploaded": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("private_original_bk2", type=Path)
    p.add_argument("run_one_capture_log", type=Path)
    p.add_argument("run_one_image_root", type=Path)
    p.add_argument("run_two_capture_log", type=Path)
    p.add_argument("run_two_image_root", type=Path)
    args = p.parse_args()
    try:
        result = verify(args.private_original_bk2, args.run_one_capture_log,
                        args.run_one_image_root, args.run_two_capture_log,
                        args.run_two_image_root)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            zipfile.BadZipFile, RuntimeError):
        p.error("owner-local direct BK2 replay anchor check unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
