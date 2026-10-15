#!/usr/bin/env python3
"""Render a single local VH/VB instrument note as diagnostic 44.1-kHz mono WAV.

This is a host-only dry note proof-of-pipeline with integer Gaussian fetch. It combines
validated VAB tone selection, raw SPU-ADPCM decoding, fixed-point sample
stepping and an ADSR envelope. It deliberately omits PlayStation Gaussian
hardware-exact timing, per-voice pan, gain laws, reverb, polyphony and SEQ scheduling.
No game assets are included or uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import struct
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.decode_spu_adpcm import decode_spu_blocks
from tools.interpolate_spu_gaussian import gaussian_voice_sample
from tools.resolve_vab_note import resolve_note
from tools.simulate_spu_voice import (
    ADSR_MAX, RATE, SpuEnvelope, SpuSampleCursor,
)

MAX_FRAMES = RATE * 20


def render_pcm_note(
    pcm: bytes, *, adsr1: int, adsr2: int, pitch_step: int,
    loop_start: int | None, loop_end: int | None,
    hold_frames: int, tail_frames: int, gain: float = 1.0,
    interpolation: str = "gaussian",
) -> tuple[bytes, dict[str, object]]:
    """Return signed 16-bit mono output and deterministic voice diagnostics.

    Frame 0 triggers key-on; key-off is applied *before* frame hold_frames.
    Stop early on ADSR completion or a one-shot sample end, and write silence
    for any unfilled portion of the explicitly requested render duration.
    """
    if not pcm or len(pcm) % 2:
        raise ValueError("PCM must contain nonempty signed 16-bit samples")
    if type(hold_frames) is not int or not 1 <= hold_frames <= MAX_FRAMES:
        raise ValueError("hold_frames must be an integer in 1..882000")
    if type(tail_frames) is not int or not 0 <= tail_frames <= MAX_FRAMES:
        raise ValueError("tail_frames must be an integer in 0..882000")
    if hold_frames + tail_frames > MAX_FRAMES:
        raise ValueError("render duration must not exceed 20 seconds")
    if type(gain) is not float and type(gain) is not int:
        raise ValueError("gain must be a real number in 0..1")
    if isinstance(gain, bool) or not math.isfinite(gain) or not 0 <= gain <= 1:
        raise ValueError("gain must be a finite number in 0..1")

    if interpolation not in ("gaussian", "nearest"):
        raise ValueError("interpolation must be gaussian or nearest")
    samples = struct.unpack("<" + "h" * (len(pcm) // 2), pcm)
    envelope = SpuEnvelope(adsr1, adsr2)
    cursor = SpuSampleCursor(
        length=len(pcm) // 2,
        loop_start=-1 if loop_start is None else loop_start,
        loop_end=-1 if loop_end is None else loop_end,
        pitch_step=pitch_step,
    )
    output = bytearray()
    frames_active = 0
    for frame in range(hold_frames + tail_frames):
        if frame == hold_frames:
            envelope.key_off()
        sample = 0
        if cursor.active and envelope.phase != "off":
            # Read at the *pre-advance* cursor, as in pc_spu.c. This first
            # Gaussian mode uses the original 512 integer coefficients and
            # wrap-aware history. Nearest is available for regression tests.
            sample = (gaussian_voice_sample(samples, cursor)
                      if interpolation == "gaussian"
                      else samples[cursor.index])
            if envelope.advance():
                sample = int(sample * (envelope.level / ADSR_MAX) * gain)
                sample = max(-32768, min(32767, sample))
                cursor.advance()
                frames_active += 1
            else:
                sample = 0
        output += struct.pack("<h", sample)

    return bytes(output), {
        "frames": hold_frames + tail_frames,
        "interpolation": interpolation,
        "frames_active": frames_active,
        "looped": cursor.looped,
        "effective_pitch_step": cursor.pitch_step,
        "final_adsr_phase": envelope.phase,
        "final_adsr_level": envelope.level,
        "first_key_off_frame": hold_frames if tail_frames else None,
    }


def wav_from_mono(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(pcm)
    return buffer.getvalue()


def render_vab_note(
    vh: Path, vb: Path, *, program: int, note: int,
    hold_frames: int, tail_frames: int, gain: float = 1.0,
) -> tuple[bytes, dict[str, object]]:
    """Render one selected VAB tone without extracting an intermediate file."""
    selection = resolve_note(vh, program=program, note=note, vb=vb)
    with vb.open("rb") as stream:
        stream.seek(selection["adpcm_offset_in_vb"])
        raw = stream.read(selection["adpcm_size_bytes"])
    if len(raw) != selection["adpcm_size_bytes"]:
        raise ValueError("selected VAG was truncated during reading")
    decoded = decode_spu_blocks(raw)
    pcm, voice = render_pcm_note(
        decoded.pcm, adsr1=selection["adsr1"],
        adsr2=selection["adsr2"],
        pitch_step=selection["pitch_step_approx"],
        loop_start=decoded.loop_start_frame,
        loop_end=decoded.loop_end_frame,
        hold_frames=hold_frames, tail_frames=tail_frames, gain=gain,
        interpolation=interpolation,
    )
    report = {
        "requested_program": program,
        "note": note,
        "lookup": selection["lookup"],
        "selected_program": selection["selected_program"],
        "tone": selection["tone"],
        "vag": selection["vag"],
        "vb_bounds_verified": selection["vb_bounds_verified"],
        "adpcm_offset_in_vb": selection["adpcm_offset_in_vb"],
        "adpcm_size_bytes": len(raw),
        "adpcm_sha256": hashlib.sha256(raw).hexdigest(),
        "source_pcm_frames": decoded.frames,
        "render_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "sample_rate_hz": RATE,
        "interpolation": interpolation,
        "gain": gain,
        "loop_start_frame": decoded.loop_start_frame,
        "loop_end_frame": decoded.loop_end_frame,
        "vh_header_sha256": selection["vh_header_sha256"],
        **voice,
        "warning": (
            "Dry diagnostic note only: integer PC-port Gaussian fetch is present, "
            "channel/program/tone gain law, pan, reverb, SEQ timing or "
            "hardware pitch-table fidelity; do not treat as a game soundtrack."
        ),
    }
    return wav_from_mono(pcm), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path)
    parser.add_argument("vb", type=Path)
    parser.add_argument("output", type=Path, help="new WAV file; never overwritten")
    parser.add_argument("--program", type=int, required=True)
    parser.add_argument("--note", type=int, required=True)
    parser.add_argument("--hold-frames", type=int, required=True,
                        help="44100-Hz output frames until key-off")
    parser.add_argument("--tail-frames", type=int, required=True,
                        help="44100-Hz release frames after key-off")
    parser.add_argument("--gain", type=float, default=1.0,
                        help="additional diagnostic amplitude factor in 0..1")
    parser.add_argument("--interpolation", choices=("gaussian", "nearest"),
                        default="gaussian", help="integer 4-tap Gaussian (default) or nearest")
    args = parser.parse_args()
    try:
        if args.output.resolve() in (args.vh.resolve(), args.vb.resolve()):
            raise ValueError("output cannot overwrite source VH or VB")
        wav, report = render_vab_note(
            args.vh, args.vb, program=args.program, note=args.note,
            hold_frames=args.hold_frames, tail_frames=args.tail_frames,
            gain=args.gain, interpolation=args.interpolation,
        )
        with args.output.open("xb") as stream:
            stream.write(wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
