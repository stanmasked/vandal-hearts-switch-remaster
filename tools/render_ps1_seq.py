#!/usr/bin/env python3
"""Render a user-owned PS1 SEQ + matching VAB VH/VB to dry diagnostic WAV.

This is an offline integration probe, not a music or game playback engine.
It uses an ideal rational SEQ timeline mapped to sample frames and a
20 reusable SEQ slots and up to 2048 note-ons, with approximate\nround-robin stealing, but without SEQ repeat handling,
reverb, exact hardware pitch, or Nintendo Switch audio output.

No source asset or existing output is overwritten. No asset is uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.inspect_ps1_seq import MAX_SEQ_BYTES, parse_seq
from tools.render_vab_chord import render_vab_chord
from tools.seq_to_chord_schedule import seq_to_schedule


def render_ps1_seq(
    seq: bytes, vh: Path, vb: Path, *,
    release_frames: int = 4410,
    interpolation: str = "gaussian",
    seq_left: int = 127,
    seq_right: int = 127,
) -> tuple[bytes, dict[str, object]]:
    parsed = parse_seq(seq)
    schedule = seq_to_schedule(parsed, release_frames=release_frames)
    wav, report = render_vab_chord(
        vh, vb, schedule["voices"], interpolation=interpolation,
        seq_left=seq_left, seq_right=seq_right,
    )
    report["seq_sha256"] = parsed["sha256"]
    report["seq_ticks"] = parsed["total_ticks"]
    report["seq_ppqn"] = parsed["ppqn"]
    report["seq_initial_tempo_us_per_quarter"] = parsed[
        "initial_tempo_us_per_quarter"
    ]
    report["seq_events"] = len(parsed["events"])
    report["seq_end_frame"] = parsed["total_frames"]
    report["release_frames"] = release_frames
    report["warning"] = (
        "Synthetic-validated offline PS1 SEQ to stereo WAV diagnostic; "
        "20 reusable voice slots and round-robin stealing are modeled "
        "with approximate release lifetimes. No real audio-block SEQ "
        "scheduler, song repeats, SPU reverb or Switch audio."
    )
    return wav, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path, help="local, user-owned PS1 .SEQ")
    parser.add_argument("vh", type=Path, help="local matching VAB .VH")
    parser.add_argument("vb", type=Path, help="local matching VAB .VB")
    parser.add_argument("output", type=Path, help="new 44.1-kHz stereo WAV")
    parser.add_argument("--release-frames", type=int, default=4410)
    parser.add_argument("--interpolation", choices=("gaussian", "nearest"),
                        default="gaussian")
    parser.add_argument("--seq-left", type=int, default=127)
    parser.add_argument("--seq-right", type=int, default=127)
    args = parser.parse_args()
    try:
        if args.output.resolve() in (
            args.seq.resolve(), args.vh.resolve(), args.vb.resolve()
        ):
            raise ValueError("output path cannot alias source SEQ, VH or VB")
        if args.seq.stat().st_size > MAX_SEQ_BYTES:
            raise ValueError("SEQ exceeds 256 KiB")
        source = args.seq.read_bytes()
        wav, report = render_ps1_seq(
            source, args.vh, args.vb, release_frames=args.release_frames,
            interpolation=args.interpolation,
            seq_left=args.seq_left, seq_right=args.seq_right,
        )
        with args.output.open("xb") as destination:
            destination.write(wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
