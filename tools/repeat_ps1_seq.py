#!/usr/bin/env python3
"""Bounded PS1 SEQ replay-event expansion for offline audio diagnostics.

Models PC-port SsSeqPlay repeatCount (0=infinite, 1=once). At a clean
FF 2F loop seam the PC port resets running status/position/tick budget,
but retains channel controllers, current tempo and held voices.
This event-level model re-integrates ticks with inherited tempo; it does
not claim sample-exact timing of the PC software-SPU audio block driver.

Infinite repeats REQUIRE a finite max_frames boundary. The synthetic
event stream ends with a marked stop event and never runs unbounded.
"""
from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import MAX_SEQ_BYTES, SAMPLE_RATE, parse_seq
from tools.mix_spu_stereo import MAX_FRAMES

MAX_REPEATS = 64
MAX_EXPANDED_EVENTS = 40000


def expand_seq_repeats(
    report: dict[str, object], *,
    repeat_count: int = 1,
    max_frames: int | None = None,
) -> dict[str, object]:
    """Create a new report with tempo-aware playback and loop boundaries.

    repeat_count=0 means loop until max_frames, not a 0-play song.
    Positive repeat counts play the same track exactly N times.
    """
    if report.get("format") != "PS1 SEQ":
        raise ValueError("requires a validated PS1 SEQ report")
    if type(repeat_count) is not int or not 0 <= repeat_count <= MAX_REPEATS:
        raise ValueError("repeat_count must be an integer in 0..64")
    if repeat_count == 0 and max_frames is None:
        raise ValueError("infinite repeat requires explicit max_frames")
    if max_frames is None:
        max_frames = MAX_FRAMES
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError("max_frames must be an integer in 1..882000")

    original = report["events"]
    if not original or original[-1]["type"] != "end_of_track":
        raise ValueError("SEQ report must terminate at end-of-track")
    if repeat_count == 0 and report["total_ticks"] == 0:
        raise ValueError("zero-duration SEQ cannot loop infinitely")

    events = []
    current_time = Fraction()
    absolute_ticks = 0
    tempo = report["initial_tempo_us_per_quarter"]
    ppqn = report["ppqn"]
    cycles = 0
    stopped_by_window = False

    while repeat_count == 0 or cycles < repeat_count:
        old_tick = 0
        for source in original:
            if len(events) >= MAX_EXPANDED_EVENTS:
                raise ValueError("expanded SEQ exceeds 40000 events")
            delta = source["tick"] - old_tick
            if type(delta) is not int or delta < 0:
                raise ValueError("nonmonotonic SEQ source ticks")
            absolute_ticks += delta
            current_time += Fraction(delta * tempo * SAMPLE_RATE,
                                     ppqn * 1000000)
            old_tick = source["tick"]
            frame = current_time.numerator // current_time.denominator

            if repeat_count == 0 and (
                frame >= max_frames and source["type"] != "end_of_track"
            ):
                stopped_by_window = True
                break
            if repeat_count == 0 and frame >= max_frames:
                stopped_by_window = True
                break
            if frame > max_frames:
                raise ValueError("finite SEQ exceeds max_frames; increase within 20 s")

            event = dict(source, tick=absolute_ticks, frame=frame,
                         cycle=cycles)
            if source["type"] == "tempo":
                tempo = source["tempo_us_per_quarter"]
            elif source["type"] == "end_of_track":
                # Clean seam: no NoteOff; retain held voices, channel state
                # and current tempo for next iteration.
                cycles += 1
                if repeat_count == 0 or cycles < repeat_count:
                    event["type"] = "loop_boundary"
            events.append(event)
        if stopped_by_window:
            break
        # End-of-track has already advanced cycles. An invalid report
        # that never reaches it would otherwise cause an infinite loop.
        if not events or events[-1]["type"] not in ("loop_boundary", "end_of_track"):
            raise ValueError("SEQ cycle does not reach end-of-track")

    if stopped_by_window:
        events.append({
            "tick": absolute_ticks,
            "frame": max_frames,
            "type": "end_of_track",
            "truncated_by_window": True,
            "cycle": cycles,
        })
    if not events or events[-1]["type"] != "end_of_track":
        raise ValueError("expanded SEQ did not terminate")

    return {
        **report,
        "events": events,
        "total_ticks": events[-1]["tick"],
        "total_frames": events[-1]["frame"],
        "original_total_ticks": report["total_ticks"],
        "original_total_frames": report["total_frames"],
        "repeat_count_requested": repeat_count,
        "cycles_completed": cycles,
        "stopped_by_window": stopped_by_window,
        "replay_window_frames": max_frames,
        "warning": (
            "Offline event-level repeat expansion. Clean loop boundaries "
            "preserve channel state, current tempo and held notes, but "
            "PC-port audio block scheduling, live SPU ADSR and hardware "
            "pitch are not emulated."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path)
    parser.add_argument("--repeat-count", type=int, default=1,
                        help="1=once (default), 2..64 finite, 0=infinite")
    parser.add_argument("--max-frames", type=int,
                        help="44100 Hz output window, required for infinite")
    args = parser.parse_args()
    try:
        if args.seq.stat().st_size > MAX_SEQ_BYTES:
            raise ValueError("SEQ exceeds 256 KiB")
        report = expand_seq_repeats(
            parse_seq(args.seq.read_bytes()),
            repeat_count=args.repeat_count, max_frames=args.max_frames,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
