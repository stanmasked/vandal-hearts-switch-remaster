#!/usr/bin/env python3
"""Validate a CD-XA extraction report against its compressed payload (read-only)."""
from __future__ import annotations

import argparse
import json
import wave
from pathlib import Path

SECTOR_BYTES = 2304
PCM_FRAMES_PER_SECTOR = 2016
PCM_SAMPLE_RATE = 37800
SUPPORTED_CODING = "0x01"


def validate_extraction(report_path: Path, payload_path: Path, wav_path: Path | None = None) -> dict[str, object]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")

    def integer(field: str) -> int:
        value = report.get(field)
        if type(value) is not int or value < 0:
            raise ValueError(f"{field} must be a nonnegative integer")
        return value

    count = integer("audio_form2_sectors_written")
    expected_size = count * SECTOR_BYTES
    if integer("payload_bytes_written") != expected_size:
        raise ValueError("report payload byte count does not match audio-sector count")
    actual_size = payload_path.stat().st_size
    if actual_size != expected_size:
        raise ValueError(f"payload size mismatch: expected {expected_size}, got {actual_size}")
    if count == 0:
        raise ValueError("no audio sectors selected; refusing empty decode")

    coding = report.get("coding_info_counts")
    if not isinstance(coding, dict) or set(coding) != {SUPPORTED_CODING}:
        raise ValueError("unsupported or mixed XA coding profile; expected only 0x01")
    if type(coding[SUPPORTED_CODING]) is not int or coding[SUPPORTED_CODING] != count:
        raise ValueError("coding-info sector count does not match selected audio sectors")

    lbas = report.get("audio_lbas")
    offsets = report.get("audio_lba_offsets")
    if not isinstance(lbas, list) or len(lbas) != count:
        raise ValueError("audio_lbas length does not match selected sector count")
    if not isinstance(offsets, list) or len(offsets) != count:
        raise ValueError("audio_lba_offsets length does not match selected sector count")

    gaps = 0
    previous = None
    for index, (lba, entry) in enumerate(zip(lbas, offsets)):
        if type(lba) is not int or lba < 0 or (previous is not None and lba <= previous):
            raise ValueError(f"invalid or nonascending audio LBA at index {index}")
        gap = 0 if previous is None else lba - previous - 1
        if gap:
            gaps += 1
        if not isinstance(entry, dict) or entry.get("lba") != lba or (
            entry.get("payload_offset") != index * SECTOR_BYTES
        ) or entry.get("missing_source_sectors_before") != gap:
            raise ValueError(f"invalid LBA/offset mapping at index {index}")
        previous = lba
    if integer("noncontiguous_audio_transitions") != gaps:
        raise ValueError("reported number of audio gaps does not match LBA mapping")

    if wav_path is not None:
        try:
            with wave.open(str(wav_path), "rb") as wav:
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (2, 2, PCM_SAMPLE_RATE):
                    raise ValueError("WAV must be stereo 16-bit PCM at 37800 Hz")
                if wav.getcomptype() != "NONE":
                    raise ValueError("WAV must be uncompressed PCM")
                if wav.getnframes() != count * PCM_FRAMES_PER_SECTOR:
                    raise ValueError("WAV frame count does not match extracted XA sector count")
                frames_remaining = wav.getnframes()
                while frames_remaining:
                    frames = min(frames_remaining, 8192)
                    chunk = wav.readframes(frames)
                    if len(chunk) != frames * 4:
                        raise ValueError("WAV PCM content is truncated")
                    frames_remaining -= frames
        except (EOFError, wave.Error) as error:
            raise ValueError(f"invalid WAV file: {error}") from error

    return {
        "audio_sectors": count,
        "payload_bytes": actual_size,
        "pcm_frames": count * PCM_FRAMES_PER_SECTOR,
        "decoded_seconds": count * PCM_FRAMES_PER_SECTOR / PCM_SAMPLE_RATE,
        "lba_gap_transitions": gaps,
        "warning": "Duration assumes concatenated frames, not original disc playback timing.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON output from extract_cdxa_payload.py")
    parser.add_argument("payload", type=Path, help="2304-byte sound-group stream")
    parser.add_argument("--wav", type=Path, help="optional decoded WAV to verify")
    args = parser.parse_args()
    try:
        result = validate_extraction(args.report, args.payload, args.wav)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
