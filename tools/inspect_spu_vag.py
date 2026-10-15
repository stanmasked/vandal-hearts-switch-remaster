#!/usr/bin/env python3
"""Inspect a standalone Sony VAGp sample header without modifying input.

This does not parse VAB-contained, headerless SPU ADPCM samples.
"""
from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

HEADER_SIZE = 0x30
BLOCK_SIZE = 16


def inspect_vag(path: Path) -> dict[str, int | str]:
    with path.open("rb") as handle:
        header = handle.read(HEADER_SIZE)
        if len(header) != HEADER_SIZE or header[:4] != b"VAGp":
            raise ValueError("not a standalone VAGp file (VAB raw samples are not supported)")
        version, reserved, data_size, sample_rate = struct.unpack_from(">IIII", header, 4)
        if data_size == 0 or data_size % BLOCK_SIZE:
            raise ValueError("VAG ADPCM length must be a nonzero multiple of 16 bytes")
        if not 1 <= sample_rate <= 192000:
            raise ValueError("invalid VAG sample rate")
        actual_size = path.stat().st_size
        if actual_size < HEADER_SIZE + data_size:
            raise ValueError("VAG audio data is truncated")
        name = header[0x20:0x30].split(b"\\x00", 1)[0].decode("ascii", errors="replace")
        return {
            "format": "VAGp",
            "version": version,
            "reserved": reserved,
            "sample_rate": sample_rate,
            "adpcm_bytes": data_size,
            "adpcm_blocks": data_size // BLOCK_SIZE,
            "pcm_samples_nominal": data_size // BLOCK_SIZE * 28,
            "trailing_bytes": actual_size - HEADER_SIZE - data_size,
            "name": name,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        result = inspect_vag(args.file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
