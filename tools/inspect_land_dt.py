#!/usr/bin/env python3
"""Inspect or compare raw LAND_DT map texture records using the upstream PC-port layout.

This reports raw bytes only. It does not decode textures or decide whether an empty
record is a defect. Use --block for one extracted 1797-byte map block, or provide
a concatenated LAND_DT stream and --map-number / --compare-maps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

BLOCK_SIZE = 1797
TEXTURE_RECORD_COUNT = 257
TEXTURE_RECORD_SIZE = 4
CLUT_INDEX_OFFSET = TEXTURE_RECORD_COUNT * TEXTURE_RECORD_SIZE
CLUT_DATA_OFFSET = CLUT_INDEX_OFFSET + TEXTURE_RECORD_COUNT
CLUT_DATA_SIZE = 512
TARGET_GFX = (241, 243)


def _validate_gfx(gfx_ids: tuple[int, ...]) -> None:
    if not gfx_ids:
        raise ValueError("At least one GFX index is required.")
    if any(type(gfx) is not int for gfx in gfx_ids):
        raise ValueError("GFX indices must be integers.")
    if len(set(gfx_ids)) != len(gfx_ids):
        raise ValueError("GFX indices must be unique.")
    invalid_gfx = [gfx for gfx in gfx_ids if gfx < 0 or gfx >= TEXTURE_RECORD_COUNT]
    if invalid_gfx:
        raise ValueError(
            f"GFX indices must be between 0 and {TEXTURE_RECORD_COUNT - 1}; invalid: {invalid_gfx}."
        )


def _read_blocks(path: Path) -> tuple[bytes, int]:
    data = path.read_bytes()
    if not data:
        raise ValueError("Input file is empty.")
    if len(data) % BLOCK_SIZE:
        raise ValueError(
            f"Input size {len(data)} is not divisible by the {BLOCK_SIZE}-byte LAND_DT block size."
        )
    return data, len(data) // BLOCK_SIZE


def _records_for_block(block: bytes, base: int, gfx_ids: tuple[int, ...]) -> list[dict[str, object]]:
    records = []
    for gfx in gfx_ids:
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
    return records


def inspect_land_dt(
    path: Path,
    map_number: int = 2,
    single_block: bool = False,
    gfx_ids: tuple[int, ...] = TARGET_GFX,
) -> dict[str, object]:
    _validate_gfx(gfx_ids)
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

    return {
        "input": str(path),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "map_number": None if single_block else map_number,
        "single_block": single_block,
        "block_size": BLOCK_SIZE,
        "block_base_offset": base,
        "texture_records_bytes": CLUT_INDEX_OFFSET,
        "clut_index_table_offset": CLUT_INDEX_OFFSET,
        "clut_data_offset": CLUT_DATA_OFFSET,
        "clut_data_size": CLUT_DATA_SIZE,
        "records": _records_for_block(block, base, gfx_ids),
        "warning": "Raw metadata inspection only; values do not prove that a texture is missing or visually defective.",
    }


def compare_land_dt(
    path: Path,
    map_numbers: tuple[int, ...],
    gfx_ids: tuple[int, ...] = TARGET_GFX,
) -> dict[str, object]:
    """Compare selected raw records across zero-based map blocks."""
    _validate_gfx(gfx_ids)
    if len(map_numbers) < 2:
        raise ValueError("Compare mode requires at least two map numbers.")
    if len(set(map_numbers)) != len(map_numbers):
        raise ValueError("Map numbers in compare mode must be unique.")
    if any(number < 0 for number in map_numbers):
        raise ValueError("Map numbers must be non-negative.")

    data, block_count = _read_blocks(path)
    invalid_maps = [number for number in map_numbers if number >= block_count]
    if invalid_maps:
        raise ValueError(f"Map numbers {invalid_maps} are outside the input ({block_count} blocks).")

    maps = []
    by_gfx: dict[int, list[dict[str, object]]] = {gfx: [] for gfx in gfx_ids}
    for map_number in map_numbers:
        base = map_number * BLOCK_SIZE
        block = data[base:base + BLOCK_SIZE]
        records = _records_for_block(block, base, gfx_ids)
        maps.append({"map_number": map_number, "block_base_offset": base, "records": records})
        for record in records:
            by_gfx[int(record["gfx"])].append({
                "map_number": map_number,
                "raw_hex": record["raw_hex"],
                "clut_index": record["clut_index"],
            })

    differences = []
    for gfx, values in by_gfx.items():
        signatures = {(item["raw_hex"], item["clut_index"]) for item in values}
        differences.append({
            "gfx": gfx,
            "runtime_table_index": 400 + gfx,
            "differs_between_maps": len(signatures) > 1,
            "values": values,
        })

    return {
        "input": str(path),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "block_size": BLOCK_SIZE,
        "compared_map_numbers": list(map_numbers),
        "maps": maps,
        "differences": differences,
        "warning": "Raw metadata comparison only; differences do not prove a defect or establish the correct texture.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="concatenated LAND_DT blocks or one extracted block")
    parser.add_argument("--map-number", type=int, default=2, help="zero-based block index (default: 2)")
    parser.add_argument("--block", action="store_true", help="input is exactly one extracted 1797-byte block")
    parser.add_argument(
        "--compare-maps",
        type=int,
        nargs="+",
        metavar="MAP",
        help="compare records across two or more zero-based map blocks",
    )
    parser.add_argument(
        "--gfx",
        type=int,
        nargs="+",
        default=list(TARGET_GFX),
        metavar="INDEX",
        help="GFX record indices to inspect (default: 241 243; valid range: 0-256)",
    )
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    if args.block and args.compare_maps is not None:
        parser.error("--block cannot be combined with --compare-maps")
    try:
        if args.compare_maps is not None:
            report = compare_land_dt(args.input, tuple(args.compare_maps), tuple(args.gfx))
        else:
            report = inspect_land_dt(args.input, args.map_number, args.block, tuple(args.gfx))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
