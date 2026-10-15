#!/usr/bin/env python3
"""Render at most 32 scheduled local VAB notes into diagnostic stereo WAV.

The JSON voice schedule is user-authored, not an extracted SEQ. A note
selects a VAB tone, SPU-ADPCM sample and pitch; the dry mixer applies
three pan stages, PsyQ squared volume law, Gaussian interpolation and
ADSR. No reverb, voice stealing, SEQ parser or Switch playback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_spu_adpcm import decode_spu_blocks
from tools.mix_spu_stereo import (
    MAX_FRAMES, MAX_VOICES, StereoVoice, render_stereo_voices,
    seq_voice_gains, stereo_wav,
)
from tools.resolve_vab_note import resolve_note


def _integer(field: str, obj: dict, default: int | None = None) -> int:
    if field not in obj and default is None:
        raise ValueError(f"voice must specify {field}")
    val = obj.get(field, default)
    if type(val) is not int:
        raise ValueError(f"{field} must be an integer")
    return val


def render_vab_chord(
    vh: Path, vb: Path, voices: list[dict], *,
    interpolation: str = "gaussian",
    seq_left: int = 127, seq_right: int = 127,
) -> tuple[bytes, dict[str, object]]:
    """Return diagnostic 44.1-kHz 16-bit stereo WAV and non-audio audit JSON."""
    if not isinstance(voices, list) or not 1 <= len(voices) <= MAX_VOICES:
        raise ValueError("voice schedule must contain 1..32 voices")
    if interpolation not in ("gaussian", "nearest"):
        raise ValueError("interpolation must be gaussian or nearest")
    planned = []
    report_voices = []
    decoded_cache = {}
    for i, args in enumerate(voices):
        if not isinstance(args, dict):
            raise ValueError(f"voice {i} must be an object")
        allowed = {
            "program", "note", "start_frame", "hold_frames",
            "tail_frames", "velocity", "channel_volume", "channel_pan",
        }
        extra = set(args) - allowed
        if extra:
            raise ValueError(f"voice {i}: unrecognized fields: {', '.join(sorted(extra))}")
        program, note = _integer("program", args), _integer("note", args)
        start = _integer("start_frame", args, 0)
        hold = _integer("hold_frames", args)
        tail = _integer("tail_frames", args, 0)
        velocity = _integer("velocity", args, 127)
        volume = _integer("channel_volume", args, 127)
        pan = _integer("channel_pan", args, 64)
        if start < 0 or hold < 1 or tail < 0 or start + hold + tail > MAX_FRAMES:
            raise ValueError(f"voice {i}: out of range 20-second frame timeline")
        selected = resolve_note(vh, program=program, note=note, vb=vb)
        gains = seq_voice_gains(
            velocity=velocity, channel_volume=volume,
            bank_volume=selected["bank_master_volume"],
            program_volume=selected["program_volume"],
            tone_volume=selected["volume"],
            tone_pan=selected["pan"],
            program_pan=selected["program_pan"],
            channel_pan=pan, seq_left=seq_left, seq_right=seq_right,
        )
        key = (selected["adpcm_offset_in_vb"], selected["adpcm_size_bytes"])
        if key not in decoded_cache:
            with vb.open("rb") as stream:
                stream.seek(key[0])
                raw = stream.read(key[1])
            if len(raw) != key[1]:
                raise ValueError(f"voice {i}: VAG truncated during VB read")
            decoded_cache[key] = decode_spu_blocks(raw)
        decoded = decoded_cache[key]
        planned.append(StereoVoice(
            pcm=decoded.pcm, adsr1=selected["adsr1"], adsr2=selected["adsr2"],
            pitch_step=selected["pitch_step_approx"],
            loop_start=decoded.loop_start_frame, loop_end=decoded.loop_end_frame,
            start_frame=start, hold_frames=hold, tail_frames=tail,
            gain_left=gains[0], gain_right=gains[1],
        ))
        report_voices.append({
            "voice": i, "requested_program": program, "note": note,
            "selected_program": selected["selected_program"],
            "tone": selected["tone"], "vag": selected["vag"],
            "lookup": selected["lookup"],
            "start_frame": start, "hold_frames": hold, "tail_frames": tail,
            "gain_left": gains[0], "gain_right": gains[1],
            "vag_offset_in_vb": key[0], "vag_size_bytes": key[1],
        })
    length = max(v.start_frame + v.hold_frames + v.tail_frames for v in planned)
    pcm, state = render_stereo_voices(
        planned, frames=length, interpolation=interpolation
    )
    for entry, runtime in zip(report_voices, state):
        entry["active_frames"] = runtime["active_frames"]
        entry["looped"] = runtime["looped"]
    return stereo_wav(pcm), {
        "frames": length,
        "sample_rate_hz": 44100,
        "channels": 2,
        "interpolation": interpolation,
        "voices": report_voices,
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "warning": (
            "Dry synthetic-schedule stereo diagnostic; no automatic SEQ "
            "events, voice stealing, PS1 pitch-table exactness, reverb, "
            "or comparison to original game audio or Switch hardware."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path)
    parser.add_argument("vb", type=Path)
    parser.add_argument("schedule", type=Path, help="local JSON with voices array")
    parser.add_argument("output", type=Path, help="new WAV path; never overwritten")
    parser.add_argument("--interpolation", choices=("gaussian", "nearest"),
                        default="gaussian")
    parser.add_argument("--seq-left", type=int, default=127)
    parser.add_argument("--seq-right", type=int, default=127)
    args = parser.parse_args()
    try:
        if args.schedule.stat().st_size > 65536:
            raise ValueError("JSON schedule exceeds 64 KiB")
        plan = json.loads(args.schedule.read_text(encoding="utf-8"))
        if not isinstance(plan, dict) or set(plan) != {"voices"}:
            raise ValueError("schedule JSON must contain exactly a voices array")
        if args.output.resolve() in (
            args.vh.resolve(), args.vb.resolve(), args.schedule.resolve()
        ):
            raise ValueError("output cannot overwrite VH, VB or JSON schedule")
        wav, report = render_vab_chord(
            args.vh, args.vb, plan["voices"], interpolation=args.interpolation,
            seq_left=args.seq_left, seq_right=args.seq_right,
        )
        with args.output.open("xb") as destination:
            destination.write(wav)
    except (OSError, ValueError, UnicodeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
