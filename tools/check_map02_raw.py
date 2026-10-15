#!/usr/bin/env python3
"""Check the reported map-02 placeholder bytes against a local LAND_DT dump.

Read-only. No original game data is stored or distributed.
Passing this check supports only the raw-byte observation, NOT the intended
appearance of a rendered face or the correctness of map-block attribution.
"""
import argparse
import hmac
import json
from pathlib import Path

from tools.inspect_land_dt import (
    BLOCK_SIZE, CLUT_DATA_OFFSET, CLUT_DATA_SIZE, CLUT_INDEX_OFFSET,
    TEXTURE_RECORD_SIZE, inspect_land_dt,
)


def check_raw_records(report):
    errors = []
    single_flag = report.get("single_block")
    map_number = report.get("map_number")
    if type(single_flag) is not bool:
        errors.append("single_block flag must be boolean")
    elif single_flag:
        if map_number is not None:
            errors.append("single-block report must have null map_number")
    elif type(map_number) is not int or map_number != 2:
        errors.append("expected map block 2")
    base = report.get("block_base_offset")
    single_block = report.get("single_block") is True
    expected_base = 0 if single_block else 2 * BLOCK_SIZE
    if type(base) is not int or base != expected_base:
        errors.append(f"LAND_DT block base offset expected {expected_base}")
    for field, expected in (
        ("block_size", BLOCK_SIZE),
        ("texture_records_bytes", CLUT_INDEX_OFFSET),
        ("clut_index_table_offset", CLUT_INDEX_OFFSET),
        ("clut_data_offset", CLUT_DATA_OFFSET),
        ("clut_data_size", CLUT_DATA_SIZE),
    ):
        if type(report.get(field)) is not int or report[field] != expected:
            errors.append(f"LAND_DT {field} expected {expected}")
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
        if type(record.get("runtime_table_index")) is not int or record["runtime_table_index"] != 400 + gfx:
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


def check_block_hash(report, expected_hash):
    """Verify the selected block against a previously recorded SHA-256 digest."""
    if expected_hash is None:
        return []
    if not isinstance(expected_hash, str):
        return ["expected block SHA-256 must be 64 hexadecimal characters"]
    expected = expected_hash.lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        return ["expected block SHA-256 must be 64 hexadecimal characters"]
    observed = report.get("block_sha256")
    if not isinstance(observed, str) or not hmac.compare_digest(observed.lower(), expected):
        return ["selected LAND_DT block SHA-256 does not match expected"]
    return []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--block", action="store_true",
                        help="input is independently extracted map-02 block (1797 bytes)")
    parser.add_argument("--expected-block-sha256", metavar="HEX",
                        help="require the selected block to match an independently recorded SHA-256")
    args = parser.parse_args()
    # Absolute import works when invoked from the repository root with -m.
    try:
        report = inspect_land_dt(args.input, map_number=2, single_block=args.block)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    errors = check_raw_records(report) + check_block_hash(report, args.expected_block_sha256)
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
