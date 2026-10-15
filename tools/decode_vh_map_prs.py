#!/usr/bin/env python3
"""Bounds-checked equivalent of pinned src/maps/unpack.c::UnpackMapFileData.

The original game reads a 32-bit LE compressed byte count followed by a
control-bit / 1024-byte-cache stream. The original C routine does not know
the destination capacity; this read-only tool caps both input and output.
It is an independent parser, NOT yet proven against genuine M_MAP02.PRS.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

MAX_COMPRESSED_BYTES = 2 * 1024 * 1024
MAX_DECODED_BYTES = 2 * 1024 * 1024
CACHE_BYTES = 1024
INITIAL_CACHE_POS = 990


def decode_prs_stream(stream, max_output=MAX_DECODED_BYTES):
    """Decode the byte stream following the 4-byte compressed length."""
    if not (1 <= len(stream) <= MAX_COMPRESSED_BYTES):
        raise ValueError("invalid PRS compressed stream length")
    if not (0 < max_output <= MAX_DECODED_BYTES):
        raise ValueError("invalid PRS output limit")

    cache = bytearray(CACHE_BYTES)  # original scratchpad starts zeroed
    write_pos = INITIAL_CACHE_POS
    out = bytearray()
    pos = 0

    def read_byte():
        nonlocal pos
        if pos >= len(stream):
            raise ValueError("truncated PRS command")
        value = stream[pos]
        pos += 1
        return value

    def emit(value):
        nonlocal write_pos
        if len(out) >= max_output:
            raise ValueError("PRS decompression exceeds output limit")
        out.append(value)
        cache[write_pos] = value
        write_pos = (write_pos + 1) & 1023

    while pos < len(stream):
        control = read_byte()
        if control == 0:
            # The upstream C control-byte loop ends on zero.
            break
        for shift in range(8):
            if not (control & (1 << shift)):
                emit(read_byte())
                continue
            command = read_byte()
            if command < 0x80:
                # Long 10-bit absolute ring-cache offset, count 3..34.
                index = read_byte() | ((command & 3) << 8)
                count = (command >> 2) + 3
                for n in range(count):
                    emit(cache[(index + n) & 1023])
            elif command < 0xc0:
                # Short relative ring-cache offset, count 2..5.
                distance = command & 15
                count = ((command & 0x30) >> 4) + 2
                for _ in range(count):
                    emit(cache[(write_pos - distance) & 1023])
            else:
                # Literal run of 8..71 bytes, in addition to the flag.
                count = (command & 0x3f) + 8
                for _ in range(count):
                    emit(read_byte())
    return bytes(out)


def decode_map_prs(data, min_output=0, max_output=MAX_DECODED_BYTES):
    """Parse the LE byte-count wrapper and decompress with output bounds."""
    if len(data) < 5 or len(data) > MAX_COMPRESSED_BYTES + 4:
        raise ValueError("invalid map PRS file size")
    compressed_bytes = struct.unpack_from("<I", data)[0]
    if compressed_bytes < 1 or compressed_bytes > MAX_COMPRESSED_BYTES:
        raise ValueError("invalid map PRS compressed length header")
    if compressed_bytes > len(data) - 4:
        raise ValueError("truncated map PRS encoded payload")
    if any(data[4 + compressed_bytes:]):
        raise ValueError("unexpected nonzero data after compressed map stream")
    payload = decode_prs_stream(data[4:4 + compressed_bytes], max_output)
    if len(payload) < min_output:
        raise ValueError("map PRS produced fewer bytes than required map models")
    return payload


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prs", type=Path, help="user-owned M_MAP02.PRS resource")
    p.add_argument("--min-decoded", type=int, default=0)
    args = p.parse_args(argv)
    if args.prs.stat().st_size > MAX_COMPRESSED_BYTES + 4:
        p.error("map PRS input exceeds compressed-byte bound")
    try:
        decoded = decode_map_prs(args.prs.read_bytes(), args.min_decoded)
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps({
        "format": "VH_MAP_PRS_COMPRESSED",
        "compressed_size": args.prs.stat().st_size,
        "decoded_size": len(decoded),
        "decoded_sha256": hashlib.sha256(decoded).hexdigest(),
        "note": "metadata only; no decoded proprietary bytes are printed",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
