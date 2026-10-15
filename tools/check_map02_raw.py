#!/usr/bin/env python3
"""Check the reported map-02 placeholder bytes against a local LAND_DT dump.

Read-only. No original game data is stored or distributed.
Passing this check supports only the raw-byte observation, NOT the intended
appearance of a rendered face or the correctness of map-block attribution.
"""
import argparse
import json
from pathlib import Path

from tools.inspect_land_dt import BLOCK_SIZE, CLUT_INDEX_OFFSET, TEXTURE_RECORD_SIZE, inspect_land_dt


def check_raw_records(report):
    errors = []
    if report.get("map_number") != 2 and not report.get("single_block"):
        errors.append("expected map block 2")
    base = report.get("block_base_offset")
    single_block = report.get("single_block") is True
    expected_base = 0 if single_block else 2 * BLOCK_SIZE
    if type(base) is not int or base != expected_base:
        errors.append(f"LAND_DT block base offset expected {expected_base}")
    records = {}
    for record in report["records"]:
        gfx = record["gfx"]
        if gfx in records:
            errors.append(f"duplicate GFX {gfx} in inspection report")
        records[gfx] = record
    for gfx in (241, 243):
        record = records.get(gfx)
        if record is None:
            errors.append(f"missing GFX {gfx}")
            continue
        raw_bytes = record.get("bytes")
        if (not isinstance(raw_bytes, list) or len(raw_bytes) != TEXTURE_RECORD_SIZE
                or any(type(value) is not int or not 0 <= value <= 255 for value in raw_bytes)):
            errors.append(f"GFX {gfx}: invalid raw texture bytes")
        else:
            if record.get("raw_hex") != bytes(raw_bytes).hex(" "):
                errors.append(f"GFX {gfx}: raw_hex does not match bytes")
            if raw_bytes != [0, 0, 0, 0]:
                errors.append(f"GFX {gfx}: raw texture record not all zero")
        if type(record.get("clut_index")) is not int or record["clut_index"] != 0:
            errors.append(f"GFX {gfx}: CLUT index must be integer zero")
        if record["runtime_table_index"] != 400 + gfx:
            errors.append(f"GFX {gfx}: unexpected runtime table index")
        base = report.get("block_base_offset")
        if type(base) is not int or base < 0:
            errors.append("invalid LAND_DT block base offset")
        else:
            expected_record_offset = gfx * TEXTURE_RECORD_SIZE
            expected_clut_offset = CLUT_INDEX_OFFSET + gfx
            for field, expected in (
                ("block_offset", expected_record_offset),
                ("absolute_input_offset", base + expected_record_offset),
                ("clut_index_offset", expected_clut_offset),
                ("absolute_clut_index_offset", base + expected_clut_offset),
            ):
                if type(record.get(field)) is not int or record[field] != expected:
                    errors.append(f"GFX {gfx}: {field} expected {expected}")

    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--block", action="store_true",
                        help="input is independently extracted map-02 block (1797 bytes)")
    args = parser.parse_args()
    # Absolute import works when invoked from the repository root with -m.
    try:
        report = inspect_land_dt(args.input, map_number=2, single_block=args.block)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    errors = check_raw_records(report)
    print(json.dumps({
        "source_sha256": report["input_sha256"],
        "block_sha256": report["block_sha256"],
        "block_base_offset": report["block_base_offset"],
        "record_offsets": [
            {"gfx": record["gfx"], "absolute_input_offset": record["absolute_input_offset"],
             "absolute_clut_index_offset": record["absolute_clut_index_offset"]}
            for record in report["records"]
        ],
        "map_number": report["map_number"],
        "single_block": report["single_block"],
        "errors": errors,
        "interpretation": "raw metadata only; no visual conclusion",
    }, indent=2))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
