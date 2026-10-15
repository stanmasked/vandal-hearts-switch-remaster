#!/usr/bin/env python3
"""Model the PC-port's 512-output-frame SEQ advance/render ordering.

Reference: platform/pc/src/pc_spu.c PC_SpuService invokes
PC_SeqAdvanceSamples(512) BEFORE rendering each 512-frame buffer.
libsnd.c SeqAdvanceByUsec adds all 512 frames' worth of ticks using the
tempo at the START of the block, then dispatches due events in order.
A tempo event changes the rate of subsequent blocks; it does not
recalculate the current block's tick budget. A clean loop seam resets
the remaining tick budget, but keeps tempo and MIDI channel state.

This is an explicitly selectable *software PC-port timing model* for
synthetic offline diagnostics, not PlayStation hardware timing or an
OpenAL buffering/latency simulation.
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
from tools.repeat_ps1_seq import MAX_EXPANDED_EVENTS, MAX_REPEATS

SPU_BLOCK_FRAMES = 512
MAX_EVENTS_PER_BLOCK = 20000


def schedule_seq_audio_blocks(
    report: dict[str, object], *,
    repeat_count: int = 1,
    max_frames: int | None = None,
) -> dict[str, object]:
    """Return an expanded report with all events at render-block starts.

    The frame of each event is the START of the block that first saw it
    become due. Finite repeats fail if the EOT cannot be reached within
    the requested 20-second safety window. For repeat_count=0 a finite
    max_frames is mandatory, and output is hard-stopped there.
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

    originals = report["events"]
    if not originals or originals[-1]["type"] != "end_of_track":
        raise ValueError("SEQ requires a final end-of-track event")
    if repeat_count == 0 and report["total_ticks"] == 0:
        raise ValueError("zero-duration SEQ cannot loop infinitely")
    ppqn = report["ppqn"]
    tempo = report["initial_tempo_us_per_quarter"]
    if type(ppqn) is not int or ppqn <= 0:
        raise ValueError("SEQ ppqn must be positive")
    if type(tempo) is not int or tempo <= 0:
        raise ValueError("SEQ tempo must be positive")

    last_tick = 0
    deltas = []
    for item in originals:
        tick = item["tick"]
        if type(tick) is not int or tick < last_tick:
            raise ValueError("nonmonotonic source SEQ ticks")
        deltas.append(tick - last_tick)
        last_tick = tick

    position = 0
    pending_delta = deltas[0]
    tick_budget = Fraction(0)
    absolute_ticks = 0
    cycles = 0
    expanded = []
    serviced_blocks = 0

    for start in range(0, max_frames, SPU_BLOCK_FRAMES):
        serviced_blocks += 1
        # PC_SeqAdvanceSamples runs before the matching PCM block.
        # One snapshot of tempo determines the WHOLE block's budget,
        # even if FF 51 changes tempo while draining due events.
        tick_budget += Fraction(
            SPU_BLOCK_FRAMES * ppqn * 1000000, SAMPLE_RATE * tempo
        )
        guard = 0
        while pending_delta <= tick_budget:
            guard += 1
            if guard > MAX_EVENTS_PER_BLOCK:
                raise ValueError("SEQ exceeds per-block event guard")
            if len(expanded) >= MAX_EXPANDED_EVENTS:
                raise ValueError("SEQ exceeds expanded event safety limit")
            tick_budget -= pending_delta
            absolute_ticks += pending_delta
            item = originals[position]
            event = dict(item, tick=absolute_ticks, frame=start, cycle=cycles)
            if item["type"] == "tempo":
                updated_tempo = item["tempo_us_per_quarter"]
                if type(updated_tempo) is not int or updated_tempo <= 0:
                    raise ValueError("invalid tempo event")
                tempo = updated_tempo
            elif item["type"] == "end_of_track":
                cycles += 1
                if repeat_count != 0 and cycles >= repeat_count:
                    expanded.append(event)
                    return {
                        **report,
                        "events": expanded,
                        "total_ticks": absolute_ticks,
                        "total_frames": start,
                        "original_total_ticks": report["total_ticks"],
                        "original_total_frames": report["total_frames"],
                        "repeat_count_requested": repeat_count,
                        "cycles_completed": cycles,
                        "stopped_by_window": False,
                        "replay_window_frames": max_frames,
                        "timing_mode": "pc_block512",
                        "spu_block_frames": SPU_BLOCK_FRAMES,
                        "serviced_blocks": serviced_blocks,
                    }
                event["type"] = "loop_boundary"
                # Source SeqEndOfTrack restarts at the first delta,
                # discards excess tick budget but keeps tempo/state.
                tick_budget = Fraction(0)
                position = 0
                pending_delta = deltas[0]
                expanded.append(event)
                continue

            expanded.append(event)
            position += 1
            if position >= len(originals):
                raise ValueError("SEQ ended without end-of-track")
            pending_delta = deltas[position]

    if repeat_count != 0:
        raise ValueError("finite SEQ cannot reach end-of-track in max_frames")
    expanded.append({
        "tick": absolute_ticks,
        "frame": max_frames,
        "type": "end_of_track",
        "truncated_by_window": True,
        "cycle": cycles,
    })
    return {
        **report,
        "events": expanded,
        "total_ticks": absolute_ticks,
        "total_frames": max_frames,
        "original_total_ticks": report["total_ticks"],
        "original_total_frames": report["total_frames"],
        "repeat_count_requested": repeat_count,
        "cycles_completed": cycles,
        "stopped_by_window": True,
        "replay_window_frames": max_frames,
        "timing_mode": "pc_block512",
        "spu_block_frames": SPU_BLOCK_FRAMES,
        "serviced_blocks": serviced_blocks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path)
    parser.add_argument("--repeat-count", type=int, default=1,
                        help="1=once, 2..64=finite, 0=infinite with max-frames")
    parser.add_argument("--max-frames", type=int)
    args = parser.parse_args()
    try:
        if args.seq.stat().st_size > MAX_SEQ_BYTES:
            raise ValueError("SEQ exceeds 256 KiB")
        data = schedule_seq_audio_blocks(
            parse_seq(args.seq.read_bytes()),
            repeat_count=args.repeat_count, max_frames=args.max_frames,
        )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
