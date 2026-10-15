#!/usr/bin/env python3
"""Render a user-owned PS1 SEQ + matching VAB VH/VB to dry diagnostic WAV.

This is an offline integration probe, not a music or game playback engine.
It uses an ideal rational SEQ timeline mapped to sample frames and a
20 reusable SEQ slots and up to 2048 note-ons, with approximate\nround-robin stealing, but with bounded SEQ repeat handling,
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
from tools.decode_spu_adpcm import decode_spu_blocks
from tools.resolve_vab_note import resolve_note
from tools.spu_voice_lifetime import SpuVoiceSpec
from tools.render_vab_chord import render_vab_chord
from tools.repeat_ps1_seq import expand_seq_repeats
from tools.seq_to_chord_schedule import seq_to_schedule


def render_ps1_seq(
    seq: bytes, vh: Path, vb: Path, *,
    release_frames: int = 4410,
    interpolation: str = "gaussian",
    seq_left: int = 127,
    seq_right: int = 127,
    repeat_count: int = 1,
    max_frames: int | None = None,
    voice_lifetime: str = "fixed",
) -> tuple[bytes, dict[str, object]]:
    original = parse_seq(seq)
    parsed = expand_seq_repeats(
        original, repeat_count=repeat_count, max_frames=max_frames,
    )
    if voice_lifetime not in ("fixed", "adsr"):
        raise ValueError("voice_lifetime must be fixed or adsr")
    spec_cache: dict[tuple[int, int], SpuVoiceSpec] = {}
    sample_cache: dict[tuple[int, int], object] = {}

    def find_voice_spec(program: int, note: int) -> SpuVoiceSpec:
        key = (program, note)
        if key not in spec_cache:
            tone = resolve_note(vh, program=program, note=note, vb=vb)
            sample_key = (tone["adpcm_offset_in_vb"], tone["adpcm_size_bytes"])
            if sample_key not in sample_cache:
                with vb.open("rb") as stream:
                    stream.seek(sample_key[0])
                    raw = stream.read(sample_key[1])
                if len(raw) != sample_key[1]:
                    raise ValueError("local VB sample truncated during ADSR inspection")
                sample_cache[sample_key] = decode_spu_blocks(raw)
            decoded = sample_cache[sample_key]
            spec_cache[key] = SpuVoiceSpec(
                adsr1=tone["adsr1"], adsr2=tone["adsr2"],
                pcm_frames=decoded.frames,
                pitch_step=tone["pitch_step_approx"],
                loop_start=decoded.loop_start_frame,
                loop_end=decoded.loop_end_frame,
            )
        return spec_cache[key]

    schedule = seq_to_schedule(
        parsed, release_frames=release_frames,
        voice_spec_for_note=find_voice_spec if voice_lifetime == "adsr" else None,
    )
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
    report["voice_lifetime_model"] = voice_lifetime
    report["repeat_count_requested"] = repeat_count
    report["repeat_cycles_completed"] = parsed["cycles_completed"]
    report["repeat_window_stop"] = parsed["stopped_by_window"]
    report["release_frames"] = release_frames
    report["warning"] = (
        "Offline PS1 SEQ stereo WAV diagnostic with event-level bounded "
        "repeat expansion, 20 reused music slots, approximate release "
        "lifetimes. No hardware-accurate SEQ block scheduling, reverb "
        "or Switch audio."
    )
    return wav, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path, help="local, user-owned PS1 .SEQ")
    parser.add_argument("vh", type=Path, help="local matching VAB .VH")
    parser.add_argument("vb", type=Path, help="local matching VAB .VB")
    parser.add_argument("output", type=Path, help="new 44.1-kHz stereo WAV")
    parser.add_argument("--release-frames", type=int, default=4410)
    parser.add_argument("--repeat-count", type=int, default=1,
                        help="1=once, 2..64=finite, 0=infinite within max-frames")
    parser.add_argument("--max-frames", type=int,
                        help="44100 Hz frame limit, mandatory for infinite repeats")
    parser.add_argument("--interpolation", choices=("gaussian", "nearest"),
                        default="gaussian")
    parser.add_argument("--voice-lifetime", choices=("fixed", "adsr"),
                        default="fixed",
                        help="fixed tail (legacy) or actual SPU ADSR/PCM liveness")
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
            repeat_count=args.repeat_count, max_frames=args.max_frames,
            voice_lifetime=args.voice_lifetime,
        )
        with args.output.open("xb") as destination:
            destination.write(wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
