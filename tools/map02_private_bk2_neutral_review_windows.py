#!/usr/bin/env python3
"""Owner-private BK2 neutral-button intervals to PLAN visual review.

A no-button interval is NOT evidence of loading, a scene boundary, or MAP02.
No PNG, emulator, disc/BIOS or gameplay screen is examined here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import zipfile

from tools.inspect_map02_private_bk2 import (
    MAX_FRAMES, MAX_FRAME_LENGTH, MAX_INPUT_BYTES,
    check_logkey, parse_header, parse_sync, read_frame, read_small,
    safe_members,
)
from tools.verify_map02_direct_private_bk2_anchor import (
    EXPECTED_CHANGES, EXPECTED_FRAMES, EXPECTED_FIRST_START,
    EXPECTED_PRESSES, MAX_BK2_ARCHIVE,
)

SCHEMA = "vh.map02.private-bk2-neutral-review-windows.v1"
DEFAULT_MINIMUM = 180
DEFAULT_MAXIMUM = 1800
DEFAULT_LIMIT = 20
MAX_LIMIT = 50


class NeutralReviewCollector:
    """Bounded candidate points with a button-held frame at BOTH edges."""

    def __init__(self, minimum=DEFAULT_MINIMUM, maximum=DEFAULT_MAXIMUM,
                 limit=DEFAULT_LIMIT, after=1663, before=EXPECTED_FRAMES):
        if (any(type(v) is not int for v in (minimum, maximum, limit, after, before))
                or not 2 <= minimum <= maximum <= 24000
                or not 1 <= limit <= MAX_LIMIT
                or not 1663 <= after < before <= EXPECTED_FRAMES):
            raise ValueError("invalid bounded neutral-review configuration")
        self.minimum, self.maximum = minimum, maximum
        self.limit, self.after, self.before = limit, after, before
        self._neutral_begin = None
        self._saw_buttons = False
        self._previous = -1
        self._windows = []

    def push(self, index: int, held: frozenset[str]) -> None:
        if type(index) is not int or index != self._previous + 1:
            raise ValueError("non-contiguous BK2 input frame stream")
        if not isinstance(held, frozenset):
            raise ValueError("expected decoded button-state set")
        self._previous = index
        if not held:
            if self._neutral_begin is None:
                self._neutral_begin = index
            return
        if self._neutral_begin is not None and self._saw_buttons:
            begin, end = self._neutral_begin, index
            span = end - begin
            if (self.minimum <= span <= self.maximum
                    and begin >= self.after
                    and end < self.before):
                self._windows.append({
                    "first_neutral_input_frame_zero_based": begin,
                    "first_following_button_frame_zero_based": end,
                    "neutral_input_frames": span,
                    "suggested_local_review_input_indices_zero_based": [
                        begin - 1, begin + (span - 1) // 2, end
                    ],
                })
        self._neutral_begin = None
        self._saw_buttons = True

    def ranked(self) -> list[dict]:
        # Deliberately never include initial or terminal no-button runs:
        # both sides must be bounded by a visible-in-input held-button frame.
        ranked = sorted(
            self._windows,
            key=lambda item: (-item["neutral_input_frames"],
                              item["first_neutral_input_frame_zero_based"])
        )
        return ranked[:self.limit]


def inspect_movie(private_movie: Path, *, minimum=DEFAULT_MINIMUM,
                  maximum=DEFAULT_MAXIMUM, limit=DEFAULT_LIMIT,
                  after=1663, before=EXPECTED_FRAMES) -> dict:
    collector = NeutralReviewCollector(
        minimum=minimum, maximum=maximum, limit=limit, after=after,
        before=before)
    movie = Path(private_movie)
    if movie.is_symlink() or not movie.is_file():
        raise ValueError("source must be regular and not a symlink")
    info = movie.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BK2_ARCHIVE:
        raise ValueError("source archive exceeds bounded size")
    with zipfile.ZipFile(movie) as archive:
        safe_members(archive)
        parse_header(read_small(archive, "Header.txt"))
        parse_sync(read_small(archive, "SyncSettings.json"))
        with archive.open("Input Log.txt") as source:
            if source.readline().strip() != b"[Input]":
                raise ValueError("BK2 input block missing")
            check_logkey(source.readline())
            count = input_bytes = changes = presses = analog_frames = 0
            first_start = None
            previous = frozenset()
            ended = False
            for raw in source:
                input_bytes += len(raw)
                if input_bytes > MAX_INPUT_BYTES or len(raw) > MAX_FRAME_LENGTH + 2:
                    raise ValueError("source movie input exceeds safety limit")
                line = raw.rstrip(b"\r\n")
                if line == b"[/Input]":
                    ended = True
                    break
                axes, held = read_frame(line)
                if count >= MAX_FRAMES:
                    raise ValueError("source frame count exceeds limit")
                collector.push(count, held)
                if held != previous:
                    changes += 1
                    new = held - previous
                    presses += len(new)
                    if first_start is None and "Start" in new:
                        first_start = count
                if axes != (128, 128, 128, 128):
                    analog_frames += 1
                count += 1
                previous = held
            if not ended or source.read(1):
                raise ValueError("source BK2 lacks end marker or contains extra bytes")
    if (count != EXPECTED_FRAMES or changes != EXPECTED_CHANGES
            or presses != EXPECTED_PRESSES or first_start != EXPECTED_FIRST_START
            or analog_frames != 0):
        raise ValueError("owner-private BK2 aggregate fingerprint differs")
    windows = collector.ranked()
    return {
        "schema": SCHEMA,
        "source_input_frames_parsed": count,
        "source_input_aggregate_matches_prior_inspection": True,
        "selection_method": "duration_of_controller_neutral_intervals_only",
        "minimum_neutral_frames": minimum,
        "maximum_neutral_frames": maximum,
        "source_region_input_frames_zero_based": [after, before],
        "review_windows": windows,
        "returned_window_count": len(windows),
        "map02_scene_frame_identified": False,
        "any_scene_transition_authenticated": False,
        "emulator_to_movie_frame_offset_independently_verified": False,
        "video_or_screenshot_captured": False,
        "original_ps1_disc_authenticated": False,
        "real_octoshock_playback_verified": False,
        "ps1_gpu_vram_verified": False,
        "private_bk2_or_inputs_uploaded_to_github": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("--min-neutral-frames", type=int, default=DEFAULT_MINIMUM)
    parser.add_argument("--max-neutral-frames", type=int, default=DEFAULT_MAXIMUM)
    parser.add_argument("--max-windows", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--after-input-frame", type=int, default=1663)
    parser.add_argument("--before-input-frame", type=int, default=EXPECTED_FRAMES)
    args = parser.parse_args()
    try:
        result = inspect_movie(
            args.owner_private_bk2, minimum=args.min_neutral_frames,
            maximum=args.max_neutral_frames, limit=args.max_windows,
            after=args.after_input_frame, before=args.before_input_frame,
        )
    except (OSError, ValueError, TypeError, UnicodeError, KeyError,
            zipfile.BadZipFile, RuntimeError):
        parser.error("owner-private neutral-input review scan unavailable")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
