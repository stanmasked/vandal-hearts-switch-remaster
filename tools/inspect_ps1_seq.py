#!/usr/bin/env python3
"""Bounded, read-only parser for Sony PlayStation single-track SEQ (pQES).

PS1 SEQ is NOT a Standard MIDI File. Its 15-byte header has big-endian
PPQN and three-byte microseconds-per-quarter tempo. Meta FF 51 uses three
raw tempo bytes WITHOUT an SMF length. Delta times use MIDI-like VLQ.
The host PC port only accepts FF 51 and FF 2F meta events.

The parser does not render audio, bind a VAB or schedule voices. It emits
ordered events with absolute musical ticks and deterministic 44100-Hz
frame positions, using exact rational arithmetic between tempo changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

SEQ_HEADER_SIZE = 15
MAX_SEQ_BYTES = 0x40000
MAX_EVENTS = 20000
SAMPLE_RATE = 44100
DEFAULT_PPQN = 480
DEFAULT_TEMPO = 500000


def _vlq(source: bytes, position: int) -> tuple[int, int]:
    value = 0
    for i in range(4):
        if position >= len(source):
            raise ValueError("truncated SEQ delta-time VLQ")
        b = source[position]
        position += 1
        value = (value << 7) | (b & 0x7f)
        if not b & 0x80:
            return value, position
    raise ValueError("SEQ delta-time VLQ exceeds four bytes")


def _data(source: bytes, position: int, count: int) -> tuple[list[int], int]:
    if position + count > len(source):
        raise ValueError("truncated SEQ event payload")
    values = list(source[position:position + count])
    if any(b & 0x80 for b in values):
        raise ValueError("unexpected MIDI status byte in SEQ event payload")
    return values, position + count


def parse_seq(source: bytes) -> dict[str, object]:
    if not isinstance(source, bytes):
        raise ValueError("SEQ input must be bytes")
    if len(source) < SEQ_HEADER_SIZE or len(source) > MAX_SEQ_BYTES:
        raise ValueError("SEQ must contain a 15-byte header and be at most 256 KiB")
    if source[:4] != b"pQES":
        raise ValueError("invalid PS1 SEQ pQES signature")

    ppqn = int.from_bytes(source[8:10], "big") or DEFAULT_PPQN
    initial_tempo = int.from_bytes(source[10:13], "big") or DEFAULT_TEMPO
    tempo = initial_tempo
    position = SEQ_HEADER_SIZE
    tick = 0
    frame_time = Fraction(0)
    running = None
    events: list[dict[str, object]] = []
    completed = False
    for _ in range(MAX_EVENTS):
        delta, position = _vlq(source, position)
        tick += delta
        frame_time += Fraction(delta * tempo * SAMPLE_RATE, ppqn * 1000000)
        frame = frame_time.numerator // frame_time.denominator

        if position >= len(source):
            raise ValueError("missing SEQ event after delta-time")
        if source[position] & 0x80:
            status = source[position]
            position += 1
            running = status if 0x80 <= status <= 0xEF else None
        else:
            if running is None:
                raise ValueError("SEQ running status missing previous channel status")
            status = running
        channel = status & 0x0F
        kind = status & 0xF0
        event = {"tick": tick, "frame": frame, "offset": position, "status": status}

        if 0x80 <= status <= 0xEF:
            count = 1 if kind in (0xC0, 0xD0) else 2
            payload, position = _data(source, position, count)
            event["channel"] = channel
            if kind == 0x80:
                event.update(type="note_off", note=payload[0], velocity=payload[1])
            elif kind == 0x90:
                event.update(
                    type="note_on" if payload[1] else "note_off",
                    note=payload[0], velocity=payload[1]
                )
            elif kind == 0xB0:
                event.update(type="control_change", controller=payload[0],
                             value=payload[1])
            elif kind == 0xC0:
                event.update(type="program_change", program=payload[0])
            else:
                event.update(type="ignored_channel_event", data=payload)
        elif status == 0xFF:
            if position >= len(source):
                raise ValueError("truncated PS1 SEQ meta type")
            meta = source[position]
            position += 1
            if meta == 0x2F:
                event.update(type="end_of_track")
                completed = True
            elif meta == 0x51:
                if position + 3 > len(source):
                    raise ValueError("truncated PS1 SEQ tempo (needs 3 raw bytes)")
                tempo = int.from_bytes(source[position:position + 3], "big") or DEFAULT_TEMPO
                position += 3
                event.update(type="tempo", tempo_us_per_quarter=tempo)
            else:
                raise ValueError(f"unsupported PS1 SEQ meta type 0x{meta:02x}")
        else:
            raise ValueError(f"unsupported SEQ system status 0x{status:02x}")

        events.append(event)
        if completed:
            break
    if not completed:
        raise ValueError("SEQ lacks end-of-track within event safety limit")

    return {
        "format": "PS1 SEQ",
        "header_version_hex": source[4:8].hex(),
        "ppqn": ppqn,
        "initial_tempo_us_per_quarter": initial_tempo,
        "rhythm_hex": source[13:15].hex(),
        "byte_length": len(source),
        "sha256": hashlib.sha256(source).hexdigest(),
        "consumed_bytes": position,
        "trailing_bytes": len(source) - position,
        "total_ticks": tick,
        "total_frames": frame,
        "sample_rate_hz": SAMPLE_RATE,
        "events": events,
        "warning": (
            "Read-only event inspection and ideal rational tick-to-frame "
            "conversion, not proof of PC audio block timing, real VAB "
            "binding, voice stealing, or Switch playback."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seq", type=Path, help="user-owned local pQES SEQ file")
    args = parser.parse_args()
    try:
        if args.seq.stat().st_size > MAX_SEQ_BYTES:
            raise ValueError("SEQ exceeds 256 KiB input safety limit")
        result = parse_seq(args.seq.read_bytes())
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
