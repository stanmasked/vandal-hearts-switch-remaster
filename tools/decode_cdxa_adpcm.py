#!/usr/bin/env python3
"""Decode standard 4-bit CD-XA stereo sector payloads to PCM WAV.

Input: concatenated 2324-byte Mode 2 Form 2 payloads, each containing 2304
bytes of XA sound groups and 20 trailing padding bytes. This supports the
common 4-bit stereo, 37.8 kHz profile only; it is not a general XA decoder.
"""
import argparse
import os
import struct
import tempfile
import wave
from pathlib import Path

SECTOR_PAYLOAD = 2324
AUDIO_BYTES_PER_SECTOR = 2304
GROUP_SIZE = 128
GROUPS_PER_SECTOR = 18
SAMPLE_RATE = 37800
K0 = (0, 60, 115, 98)
K1 = (0, 0, -52, -55)


def decode_group(frame: bytes, history: list[list[int]]) -> bytes:
    """Decode one 128-byte, 4-bit stereo XA sound group.

    The four parameter pairs are stored at bytes 4..11; bytes 0..3 and
    12..15 are their duplicate copies. Each of the four 28-sample chunks
    stores left/right nibbles in the same byte, low nibble first.
    """
    if len(frame) != GROUP_SIZE:
        raise ValueError("XA sound group must be exactly 128 bytes")
    if frame[0:4] != frame[4:8] or frame[8:12] != frame[12:16]:
        raise ValueError("XA sound-parameter copies do not match")

    channels: list[list[int]] = [[], []]
    for chunk in range(4):
        for channel in range(2):
            param = frame[4 + chunk * 2 + channel]
            filt, low_shift = (param >> 4) & 0x0F, param & 0x0F
            if filt >= len(K0):
                raise ValueError(f"invalid XA filter {filt}")
            shift = 12 - low_shift
            if shift < 0:
                raise ValueError(f"invalid XA shift {low_shift}")
            h1, h2 = history[channel]
            for row in range(28):
                packed = frame[16 + row * 4 + chunk]
                nibble = (packed >> 4) & 0x0F if channel else packed & 0x0F
                signed_nibble = nibble if nibble < 8 else nibble - 16
                sample = signed_nibble * (1 << shift)
                sample += (K0[filt] * h1 + K1[filt] * h2 + 32) >> 6
                # Match the common XA decoder reference behavior: keep the
                # predictor history unclipped, and clamp only the emitted PCM.
                h2, h1 = h1, sample
                channels[channel].append(max(-32768, min(32767, sample)))
            history[channel] = [h1, h2]

    pcm = bytearray()
    for row in range(112):
        pcm.extend(struct.pack("<hh", channels[0][row], channels[1][row]))
    return bytes(pcm)

def decode_payload_file(
    source: Path, destination: Path, sectors: int | None = None,
    extracted_groups: bool = False,
) -> dict[str, int]:
    source_resolved = source.resolve()
    destination_resolved = destination.resolve()
    if source_resolved == destination_resolved or (
        source.exists() and destination.exists() and source.samefile(destination)
    ):
        raise ValueError("output must not overwrite the input payload")
    size = source.stat().st_size
    if size == 0:
        raise ValueError("input payload is empty")
    sector_size = AUDIO_BYTES_PER_SECTOR if extracted_groups else SECTOR_PAYLOAD
    if size % sector_size:
        raise ValueError(f"input size must be divisible by {sector_size} bytes")
    available = size // sector_size
    count = available if sectors is None else sectors
    if count < 1 or count > available:
        raise ValueError(f"sector count must be between 1 and {available}")
    history = [[0, 0], [0, 0]]
    groups = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=f".{destination.name}.", suffix=".tmp",
            dir=destination.parent, delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        with source.open("rb") as src, wave.open(str(temp_path), "wb") as dst:
            dst.setnchannels(2)
            dst.setsampwidth(2)
            dst.setframerate(SAMPLE_RATE)
            for sector_index in range(count):
                sector = src.read(sector_size)
                if len(sector) != sector_size:
                    raise ValueError(f"incomplete payload sector {sector_index}")
                audio = sector[:AUDIO_BYTES_PER_SECTOR]
                padding = sector[AUDIO_BYTES_PER_SECTOR:] if not extracted_groups else b""
                if any(padding):
                    raise ValueError(f"non-zero padding in payload sector {sector_index}")
                pcm = bytearray()
                for offset in range(0, AUDIO_BYTES_PER_SECTOR, GROUP_SIZE):
                    pcm.extend(decode_group(audio[offset:offset + GROUP_SIZE], history))
                    groups += 1
                dst.writeframesraw(pcm)
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
    return {"sectors": count, "groups": groups, "frames": groups * 112}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sectors", type=int, help="number of sectors to decode (default: all)")
    parser.add_argument(
        "--extracted-groups", action="store_true",
        help="input is the 2304-byte-per-sector stream from extract_cdxa_payload.py",
    )
    args = parser.parse_args()
    try:
        report = decode_payload_file(args.payload, args.output, args.sectors, args.extracted_groups)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Decoded sectors: {report['sectors']}")
    print(f"Decoded sound groups: {report['groups']}")
    print(f"PCM frames: {report['frames']} at {SAMPLE_RATE} Hz")
    print(f"Output: {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
