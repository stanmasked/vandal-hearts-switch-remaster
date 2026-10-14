#!/usr/bin/env python3
"""Inspect LAND_DT map texture records using the layout documented by the upstream PC port.

This reports raw bytes only. It does not decode textures or decide whether an empty
record is a defect. Use --block for one extracted 1797-byte map block, or provide
a concatenated LAND_DT stream and --map-number.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

BLOCK_SIZE = 1797
TEXTURE_RECORD_COUNT = 257
TEXTURE_RECORD_SIZE = 4
CLUT_INDEX_OFFSET = TEXTURE_RECORD_COUNT * TEXTURE_RECORD_SIZE
CLUT_DATA_OFFSET = CLUT_INDEX_OFFSET + TEXTURE_RECORD_COUNT
CLUT_DATA_SIZE = 512
TARGET_GFX = (241, 243)


def inspect_land_dt(path: Path, map_number: int = 2, single_block: bool = False) -> dict[str, object]:
    data = path.read_bytes()
    if not data:
        raise ValueError("Input file is empty.")

    if single_block:
        if len(data) != BLOCK_SIZE:
            raise ValueError(f"Single-block input must be exactly {BLOCK_SIZE} bytes; got {len(data)}.")
        base = 0
    else:
        if len(data) % BLOCK_SIZE:
            raise ValueError(
                f"Input size {len(data)} is not divisible by the {BLOCK_SIZE}-byte LAND_DT block size."
            )
        block_count = len(data) // BLOCK_SIZE
        if map_number < 0 or map_number >= block_count:
            raise ValueError(f"Map number {map_number} is outside the input ({block_count} blocks).")
        base = map_number * BLOCK_SIZE

    block = data[base:base + BLOCK_SIZE]
    if len(block) != BLOCK_SIZE:
        raise ValueError("Selected LAND_DT block is incomplete.")

    records = []
    for gfx in TARGET_GFX:
        offset = gfx * TEXTURE_RECORD_SIZE
        raw = block[offset:offset + TEXTURE_RECORD_SIZE]
        records.append({
            "gfx": gfx,
            "runtime_table_index": 400 + gfx,
            "block_offset": offset,
            "absolute_input_offset": base + offset,
            "raw_hex": raw.hex(" "),
            "bytes": list(raw),
            "clut_index_offset": CLUT_INDEX_OFFSET + gfx,
            "clut_index": block[CLUT_INDEX_OFFSET + gfx],
        })

    return {
        "input": str(path),
        "map_number": None if single_block else map_number,
        "single_block": single_block,
        "block_size": BLOCK_SIZE,
        "block_base_offset": base,
        "texture_records_bytes": CLUT_INDEX_OFFSET,
        "clut_index_table_offset": CLUT_INDEX_OFFSET,
        "clut_data_offset": CLUT_DATA_OFFSET,
        "clut_data_size": CLUT_DATA_SIZE,
        "records": records,
        "warning": "Raw metadata inspection only; values do not prove that a texture is missing or visually defective.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="concatenated LAND_DT blocks or one extracted block")
    parser.add_argument("--map-number", type=int, default=2, help="zero-based block index in concatenated input (default: 2)")
    parser.add_argument("--block", action="store_true", help="input is exactly one extracted 1797-byte block")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    try:
        report = inspect_land_dt(args.input, args.map_number, args.block)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
