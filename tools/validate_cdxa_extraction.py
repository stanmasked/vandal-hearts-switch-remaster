#!/usr/bin/env python3
"""Validate a CD-XA extraction report against its compressed payload (read-only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path

SECTOR_BYTES = 2304
PCM_FRAMES_PER_SECTOR = 2016
PCM_SAMPLE_RATE = 37800
SUPPORTED_CODING = "0x01"
RAW_SECTOR_BYTES = 2352
RAW_SYNC = bytes([0]) + bytes([255]) * 10 + bytes([0])


def validate_extraction(report_path: Path, payload_path: Path, wav_path: Path | None = None, source_bin: Path | None = None) -> dict[str, object]:
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
    expected_digest = report.get("payload_sha256")
    if not isinstance(expected_digest, str) or len(expected_digest) != 64 or any(
        letter not in "0123456789abcdef" for letter in expected_digest
    ):
        raise ValueError("report must include a lowercase SHA-256 payload digest")
    digest = hashlib.sha256()
    with payload_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_digest:
        raise ValueError("payload SHA-256 mismatch; file may not belong to this report")

    coding = report.get("coding_info_counts")
    if not isinstance(coding, dict) or set(coding) != {SUPPORTED_CODING}:
        raise ValueError("unsupported or mixed XA coding profile; expected only 0x01")
    if type(coding[SUPPORTED_CODING]) is not int or coding[SUPPORTED_CODING] != count:
        raise ValueError("coding-info sector count does not match selected audio sectors")

    streams = report.get("file_channel_counts")
    if not isinstance(streams, dict) or not streams:
        raise ValueError("report must include CD-XA file/channel counts")
    if len(streams) != 1:
        raise ValueError(
            "multiple CD-XA file/channel streams selected; extract a single "
            "stream using --file-number and --channel before decoding"
        )
    stream_key, stream_count = next(iter(streams.items()))
    parts = stream_key.split(":") if isinstance(stream_key, str) else []
    if len(parts) != 2 or any(
        not part.isdecimal() or not 0 <= int(part) <= 255 or str(int(part)) != part
        for part in parts
    ) or type(stream_count) is not int or stream_count != count:
        raise ValueError("invalid CD-XA file/channel count metadata")

    lbas = report.get("audio_lbas")
    offsets = report.get("audio_lba_offsets")
    if not isinstance(lbas, list) or len(lbas) != count:
        raise ValueError("audio_lbas length does not match selected sector count")
    if not isinstance(offsets, list) or len(offsets) != count:
        raise ValueError("audio_lba_offsets length does not match selected sector count")

    # The extractor records absolute disc LBAs and the exact scanned range.
    # When present, these fields must agree with every selected audio sector.
    range_fields = ("start_lba", "sectors_scanned", "first_audio_lba", "last_audio_lba")
    if any(field in report for field in range_fields):
        if not all(field in report for field in range_fields):
            raise ValueError("incomplete source LBA range metadata")
        scan_start = integer("start_lba")
        scanned = integer("sectors_scanned")
        if scanned == 0:
            raise ValueError("sectors_scanned must be positive")
        if (type(report["first_audio_lba"]) is not int
                or type(report["last_audio_lba"]) is not int):
            raise ValueError("first/last audio LBA must be integers")
        if report["first_audio_lba"] != lbas[0] or report["last_audio_lba"] != lbas[-1]:
            raise ValueError("first/last audio LBA does not match sector list")
        if not (scan_start <= lbas[0] <= lbas[-1] < scan_start + scanned):
            raise ValueError("audio LBA outside reported scanned range")
        if count > scanned:
            raise ValueError("selected audio sector count exceeds scanned range")

    gaps = 0
    previous = None
    for index, (lba, entry) in enumerate(zip(lbas, offsets)):
        if type(lba) is not int or lba < 0 or (previous is not None and lba <= previous):
            raise ValueError(f"invalid or nonascending audio LBA at index {index}")
        gap = 0 if previous is None else lba - previous - 1
        if gap:
            gaps += 1
        if not isinstance(entry, dict) or any(
            type(entry.get(field)) is not int
            for field in ("lba", "payload_offset", "missing_source_sectors_before")
        ) or entry["lba"] != lba or (
            entry["payload_offset"] != index * SECTOR_BYTES
        ) or entry["missing_source_sectors_before"] != gap:
            raise ValueError(f"invalid LBA/offset mapping at index {index}")
        previous = lba
    if integer("noncontiguous_audio_transitions") != gaps:
        raise ValueError("reported number of audio gaps does not match LBA mapping")

    if source_bin is not None:
        # Scan the actual source range and verify every selected sector.
        # This also catches unreported eligible sectors between listed LBAs.
        if not all(field in report for field in range_fields):
            raise ValueError("source BIN verification requires scan-range metadata")
        raw_size = source_bin.stat().st_size
        if raw_size % RAW_SECTOR_BYTES:
            raise ValueError("source BIN is not aligned to 2352-byte sectors")
        if scan_start + scanned > raw_size // RAW_SECTOR_BYTES:
            raise ValueError("reported scan range exceeds source BIN")
        file_number, channel_number = (int(part) for part in parts)
        selected_index = 0
        mode2_count = 0
        matching_subheaders_count = 0
        submode_counts: dict[str, int] = {}
        with source_bin.open("rb") as raw, payload_path.open("rb") as payload:
            raw.seek(scan_start * RAW_SECTOR_BYTES)
            for lba in range(scan_start, scan_start + scanned):
                sector = raw.read(RAW_SECTOR_BYTES)
                if len(sector) != RAW_SECTOR_BYTES:
                    raise ValueError(f"source BIN truncated at LBA {lba}")
                if sector[:12] != RAW_SYNC or sector[15] != 2:
                    continue
                mode2_count += 1
                header = sector[16:20]
                if header != sector[20:24]:
                    continue
                matching_subheaders_count += 1
                source_file, source_channel, submode, coding_byte = header
                submode_key = f"0x{submode:02X}"
                submode_counts[submode_key] = submode_counts.get(submode_key, 0) + 1
                if not (submode & 0x04 and submode & 0x20):
                    continue
                if (source_file, source_channel) != (file_number, channel_number):
                    continue
                if coding_byte != 0x01:
                    raise ValueError(f"unsupported coding at source LBA {lba}")
                if selected_index >= count or lbas[selected_index] != lba:
                    raise ValueError(f"source BIN selection differs from report at LBA {lba}")
                if payload.read(SECTOR_BYTES) != sector[24:2328]:
                    raise ValueError(f"source BIN payload mismatch at LBA {lba}")
                selected_index += 1
            if selected_index != count:
                raise ValueError("source BIN selection does not match report sector count")
        if (integer("mode2_sectors") != mode2_count
                or integer("matching_subheaders") != matching_subheaders_count):
            raise ValueError("source BIN sector/header counts do not match extraction report")
        if report.get("submode_counts") != submode_counts:
            raise ValueError("source BIN submode counts do not match extraction report")

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
    parser.add_argument("--source-bin", type=Path, help="optional raw source BIN for read-only verification")
    args = parser.parse_args()
    try:
        result = validate_extraction(args.report, args.payload, args.wav, args.source_bin)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
