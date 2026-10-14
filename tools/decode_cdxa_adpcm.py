#!/usr/bin/env python3
"""Decode standard 4-bit CD-XA stereo sector payloads to PCM WAV.

Input: concatenated 2324-byte Mode 2 Form 2 payloads, each containing 2304
bytes of XA sound groups and 20 trailing padding bytes. This supports the
common 4-bit stereo, 37.8 kHz profile only; it is not a general XA decoder.
"""
import argparse
import struct
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
    """Decode one 128-byte, 8-unit 4-bit stereo XA sound group."""
    if len(frame) != GROUP_SIZE:
        raise ValueError("XA sound group must be exactly 128 bytes")
    if frame[0:4] != frame[4:8] or frame[8:12] != frame[12:16]:
        raise ValueError("XA sound-parameter copies do not match")
    params = list(frame[0:4]) + list(frame[8:12])
    unit_samples: list[list[int]] = [[] for _ in range(8)]
    for unit, param in enumerate(params):
        filt, shift = (param >> 4) & 0x0F, param & 0x0F
        if filt >= len(K0):
            raise ValueError(f"invalid XA filter {filt}")
        if shift > 12:
            shift = 9
        channel = unit & 1
        h1, h2 = history[channel]
        for row in range(28):
            packed = frame[16 + row * 4 + unit // 2]
            nibble = (packed >> 4) & 0x0F if unit & 1 else packed & 0x0F
            signed_nibble = nibble if nibble < 8 else nibble - 16
            sample = (signed_nibble << 12) >> shift
            sample += (K0[filt] * h1 + K1[filt] * h2 + 32) >> 6
            sample = max(-32768, min(32767, sample))
            h2, h1 = h1, sample
            unit_samples[unit].append(sample)
        history[channel] = [h1, h2]
    pcm = bytearray()
    for row in range(28):
        for pair in range(4):
            pcm.extend(struct.pack("<hh", unit_samples[pair * 2][row],
                                   unit_samples[pair * 2 + 1][row]))
    return bytes(pcm)


def decode_payload_file(source: Path, destination: Path, sectors: int | None = None) -> dict[str, int]:
    if source.resolve() == destination.resolve():
        raise ValueError("output must not overwrite the input payload")
    size = source.stat().st_size
    if size == 0:
        raise ValueError("input payload is empty")
    if size % SECTOR_PAYLOAD:
        raise ValueError(f"input size must be divisible by {SECTOR_PAYLOAD} bytes")
    available = size // SECTOR_PAYLOAD
    count = available if sectors is None else sectors
    if count < 1 or count > available:
        raise ValueError(f"sector count must be between 1 and {available}")
    history = [[0, 0], [0, 0]]
    groups = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, wave.open(str(destination), "wb") as dst:
        dst.setnchannels(2)
        dst.setsampwidth(2)
        dst.setframerate(SAMPLE_RATE)
        for sector_index in range(count):
            sector = src.read(SECTOR_PAYLOAD)
            if len(sector) != SECTOR_PAYLOAD:
                raise ValueError(f"incomplete payload sector {sector_index}")
            audio = sector[:AUDIO_BYTES_PER_SECTOR]
            padding = sector[AUDIO_BYTES_PER_SECTOR:]
            if any(padding):
                raise ValueError(f"non-zero padding in payload sector {sector_index}")
            pcm = bytearray()
            for offset in range(0, AUDIO_BYTES_PER_SECTOR, GROUP_SIZE):
                pcm.extend(decode_group(audio[offset:offset + GROUP_SIZE], history))
                groups += 1
            dst.writeframesraw(pcm)
    return {"sectors": count, "groups": groups, "frames": groups * 28}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--sectors", type=int, help="number of sectors to decode (default: all)")
    args = parser.parse_args()
    try:
        report = decode_payload_file(args.payload, args.output, args.sectors)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Decoded sectors: {report['sectors']}")
    print(f"Decoded sound groups: {report['groups']}")
    print(f"PCM frames: {report['frames']} at {SAMPLE_RATE} Hz")
    print(f"Output: {args.output} ({args.output.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
