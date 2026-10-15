#!/usr/bin/env python3
"""Dry PS1 SPU stereo note gains and up-to-32-voice offline mixer.

Models the VandalHearts-PcPort SEQ gain order and pc_spu.c's dry
per-frame summation, without reverb, voice stealing or an SEQ event parser.
All PCM is generated or loaded locally. This is *not* a Switch backend.
"""
from __future__ import annotations

import io
import math
import struct
import wave
from dataclasses import dataclass
from typing import Sequence

from tools.interpolate_spu_gaussian import gaussian_voice_sample
from tools.simulate_spu_voice import ADSR_MAX, RATE, SpuEnvelope, SpuSampleCursor

MAX_VOICES = 32
MAX_SEQ_VOICES = 20
MAX_SCHEDULE_NOTES = 2048
MAX_FRAMES = RATE * 20


def _level(name: str, value: int) -> int:
    if type(value) is not int or not 0 <= value <= 127:
        raise ValueError(f"{name} must be an integer in 0..127")
    return value


def pan_factors(pan: int) -> tuple[float, float]:
    """Exact piecewise pan convention of PC-port PanFactors (0,64,127)."""
    _level("pan", pan)
    if pan < 64:
        return 1.0, pan / 63.0
    return (127 - pan) / 63.0, 1.0


def seq_voice_gains(
    *, velocity: int, channel_volume: int, bank_volume: int,
    program_volume: int, tone_volume: int, tone_pan: int,
    program_pan: int, channel_pan: int,
    seq_left: int = 127, seq_right: int = 127,
    trim: float = 1.012,
) -> tuple[float, float]:
    """Reference port's four successive /127 integer stages and square law.

    The gain is calculated separately for left and right *after* the
    three pan factors. Program/tone and channel volumes are not combined
    into one float upfront; intermediate truncation matters.
    """
    fields = {
        "velocity": velocity, "channel_volume": channel_volume,
        "bank_volume": bank_volume, "program_volume": program_volume,
        "tone_volume": tone_volume, "tone_pan": tone_pan,
        "program_pan": program_pan, "channel_pan": channel_pan,
        "seq_left": seq_left, "seq_right": seq_right,
    }
    for name, value in fields.items():
        _level(name, value)
    if type(trim) not in (float, int) or not math.isfinite(trim) or trim < 0 or trim > 2:
        raise ValueError("trim must be a finite number in 0..2")

    volume = velocity * channel_volume // 127
    volume = volume * bank_volume // 127
    volume = volume * program_volume // 127
    volume = volume * tone_volume // 127
    p = [pan_factors(pan) for pan in (tone_pan, program_pan, channel_pan)]
    left = (volume * seq_left // 127) / 127.0
    right = (volume * seq_right // 127) / 127.0
    for lp, rp in p:
        left *= lp
        right *= rp
    return left * left * trim, right * right * trim


@dataclass(frozen=True)
class StereoVoice:
    pcm: bytes
    adsr1: int
    adsr2: int
    pitch_step: int
    loop_start: int | None
    loop_end: int | None
    start_frame: int
    hold_frames: int
    tail_frames: int
    gain_left: float
    gain_right: float
    voice_slot: int | None = None  # optional sequencer slot 0..19


def render_stereo_voices(
    voices: Sequence[StereoVoice], *, frames: int,
    interpolation: str = "gaussian",
) -> tuple[bytes, list[dict[str, object]]]:
    """Render a fixed-length interleaved signed-16 stereo PCM stream.

    Notes key on at start_frame and key off immediately before the
    start_frame + hold_frames output sample. One-shot/ADSR termination
    silences the rest. There is no voice stealing or automatic SEQ timing.
    """
    if interpolation not in ("gaussian", "nearest"):
        raise ValueError("interpolation must be gaussian or nearest")
    if type(frames) is not int or not 1 <= frames <= MAX_FRAMES:
        raise ValueError("frames must be an integer in 1..882000")
    if not isinstance(voices, (tuple, list)) or not 1 <= len(voices) <= MAX_VOICES:
        raise ValueError("render requires 1..32 voices")

    states = []
    for number, v in enumerate(voices):
        if not isinstance(v, StereoVoice):
            raise ValueError(f"voice {number}: expected StereoVoice")
        if not v.pcm or len(v.pcm) % 2:
            raise ValueError(f"voice {number}: expected nonempty 16-bit PCM")
        if type(v.start_frame) is not int or v.start_frame < 0:
            raise ValueError(f"voice {number}: invalid start frame")
        if type(v.hold_frames) is not int or v.hold_frames < 1:
            raise ValueError(f"voice {number}: invalid hold frames")
        if type(v.tail_frames) is not int or v.tail_frames < 0:
            raise ValueError(f"voice {number}: invalid tail frames")
        if v.start_frame + v.hold_frames + v.tail_frames > frames:
            raise ValueError(f"voice {number}: timeline exceeds render duration")
        for gain in (v.gain_left, v.gain_right):
            if type(gain) not in (float, int) or not math.isfinite(gain) or not 0 <= gain <= 2:
                raise ValueError(f"voice {number}: gain must be finite in 0..2")
        env = SpuEnvelope(v.adsr1, v.adsr2)
        cursor = SpuSampleCursor(
            len(v.pcm) // 2,
            -1 if v.loop_start is None else v.loop_start,
            -1 if v.loop_end is None else v.loop_end,
            v.pitch_step,
        )
        source = struct.unpack("<" + "h" * (len(v.pcm) // 2), v.pcm)
        states.append((v, source, env, cursor, {"voice": number, "active_frames": 0}))

    output = bytearray()
    for frame in range(frames):
        left = right = 0.0
        for voice, source, env, cursor, info in states:
            elapsed = frame - voice.start_frame
            if elapsed < 0 or elapsed >= voice.hold_frames + voice.tail_frames:
                continue
            if elapsed == voice.hold_frames:
                env.key_off()
            if not cursor.active or env.phase == "off":
                continue
            sample = (gaussian_voice_sample(source, cursor)
                      if interpolation == "gaussian" else source[cursor.index])
            if not env.advance():
                continue
            level = env.level / ADSR_MAX
            left += sample * level * voice.gain_left
            right += sample * level * voice.gain_right
            cursor.advance()
            info["active_frames"] += 1
        # The reference renderer sums floats, then truncates once per
        # channel and clips the entire mix (not each individual voice).
        a = max(-32768, min(32767, int(left)))
        b = max(-32768, min(32767, int(right)))
        output += struct.pack("<hh", a, b)
    diagnostics = []
    for v, source, env, cursor, info in states:
        diagnostics.append({
            **info,
            "looped": cursor.looped,
            "final_adsr_phase": env.phase,
            "final_adsr_level": env.level,
            "effective_pitch_step": cursor.pitch_step,
            "start_frame": v.start_frame,
        })
    return bytes(output), diagnostics


def render_stereo_timeline(
    voices: Sequence[StereoVoice], *, frames: int,
    interpolation: str = "gaussian",
) -> tuple[bytes, list[dict[str, object]]]:
    """Mix up to 2048 scheduled notes over 20 reusable SEQ slots.

    At most 20 scheduled note instances can be active on any output frame.
    The timeline must explicitly truncate a stolen note so same-slot
    intervals never overlap. A strict overlap error catches broken
    schedulers rather than accidentally playing 21+ concurrent voices.
    """
    if interpolation not in ("gaussian", "nearest"):
        raise ValueError("interpolation must be gaussian or nearest")
    if type(frames) is not int or not 1 <= frames <= MAX_FRAMES:
        raise ValueError("frames must be an integer in 1..882000")
    if not isinstance(voices, (tuple, list)) or not 1 <= len(voices) <= MAX_SCHEDULE_NOTES:
        raise ValueError("timeline requires 1..2048 scheduled notes")

    starts: dict[int, list[int]] = {}
    latest_end = [-1] * MAX_SEQ_VOICES
    prepared = []
    for number, v in enumerate(voices):
        if not isinstance(v, StereoVoice):
            raise ValueError(f"voice {number}: expected StereoVoice")
        slot = v.voice_slot
        if type(slot) is not int or not 0 <= slot < MAX_SEQ_VOICES:
            raise ValueError(f"voice {number}: expected SEQ slot 0..19")
        if not v.pcm or len(v.pcm) % 2:
            raise ValueError(f"voice {number}: invalid 16-bit PCM")
        if type(v.start_frame) is not int or v.start_frame < 0:
            raise ValueError(f"voice {number}: invalid start frame")
        if type(v.hold_frames) is not int or v.hold_frames < 1:
            raise ValueError(f"voice {number}: invalid hold frames")
        if type(v.tail_frames) is not int or v.tail_frames < 0:
            raise ValueError(f"voice {number}: invalid tail frames")
        ending = v.start_frame + v.hold_frames + v.tail_frames
        if ending > frames:
            raise ValueError(f"voice {number}: timeline exceeds render duration")
        for gain in (v.gain_left, v.gain_right):
            if type(gain) not in (float, int) or not math.isfinite(gain) or not 0 <= gain <= 2:
                raise ValueError(f"voice {number}: gain must be finite in 0..2")
        # Validate chronological overlap independently of input list order
        # using a per-slot interval scan further below.
        prepared.append((
            v, struct.unpack("<" + "h" * (len(v.pcm) // 2), v.pcm),
            SpuEnvelope(v.adsr1, v.adsr2),
            SpuSampleCursor(
                len(v.pcm) // 2,
                -1 if v.loop_start is None else v.loop_start,
                -1 if v.loop_end is None else v.loop_end,
                v.pitch_step,
            ),
            {"voice": number, "voice_slot": slot, "active_frames": 0},
        ))
        starts.setdefault(v.start_frame, []).append(number)

    for number in sorted(range(len(prepared)),
                         key=lambda n: (prepared[n][0].start_frame, n)):
        v = prepared[number][0]
        slot = v.voice_slot
        if v.start_frame < latest_end[slot]:
            raise ValueError(f"voice {number}: overlapping SEQ slot {slot}")
        latest_end[slot] = v.start_frame + v.hold_frames + v.tail_frames

    active: dict[int, int] = {}
    output = bytearray()
    for frame in range(frames):
        # Expired voices are removed before new key-ons at the same frame.
        for slot, number in tuple(active.items()):
            v = prepared[number][0]
            if frame >= v.start_frame + v.hold_frames + v.tail_frames:
                del active[slot]
        for number in starts.get(frame, ()):
            v = prepared[number][0]
            if v.voice_slot in active:
                raise ValueError(f"overlap at frame {frame}, slot {v.voice_slot}")
            active[v.voice_slot] = number
        left = right = 0.0
        for slot in sorted(active):
            v, source, env, cursor, info = prepared[active[slot]]
            elapsed = frame - v.start_frame
            if elapsed == v.hold_frames:
                env.key_off()
            if not cursor.active or env.phase == "off":
                continue
            sample = (gaussian_voice_sample(source, cursor)
                      if interpolation == "gaussian" else source[cursor.index])
            if not env.advance():
                continue
            level = env.level / ADSR_MAX
            left += sample * level * v.gain_left
            right += sample * level * v.gain_right
            cursor.advance()
            info["active_frames"] += 1
        output += struct.pack(
            "<hh",
            max(-32768, min(32767, int(left))),
            max(-32768, min(32767, int(right))),
        )
    diag = [
        {**info, "looped": cursor.looped,
         "effective_pitch_step": cursor.pitch_step,
         "final_adsr_phase": env.phase,
         "final_adsr_level": env.level,
         "start_frame": v.start_frame}
        for v, source, env, cursor, info in prepared
    ]
    return bytes(output), diag


def stereo_wav(pcm: bytes) -> bytes:
    if not pcm or len(pcm) % 4:
        raise ValueError("expected nonempty 16-bit interleaved stereo PCM")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return output.getvalue()
