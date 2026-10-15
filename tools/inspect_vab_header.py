#!/usr/bin/env python3
"""Read-only structural inspection of the 32-byte Sony VAB VH header.

This deliberately does not interpret program/tone tables or VB sample offsets.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

HEADER_SIZE = 32

def inspect_vab_header(path: Path) -> dict[str, int | str]:
    with path.open("rb") as f:
        header = f.read(HEADER_SIZE)
    if len(header) < HEADER_SIZE or header[:4] != b"pBAV":
        raise ValueError("not a complete little-endian VAB VH header (pBAV)")
    version, vab_id, declared_size = struct.unpack_from("<III", header, 4)
    reserved, programs, tones, vags = struct.unpack_from("<HHHH", header, 16)
    master_volume, master_pan, bank_attr, attr2 = struct.unpack_from("<BBBB", header, 24)
    if programs > 128 or vags > 256:
        raise ValueError("VAB program or VAG count exceeds format limits")
    if declared_size and declared_size < HEADER_SIZE:
        raise ValueError("declared VAB size is smaller than its header")
    result = {
        "format": "VAB VH",
        "header_sha256": hashlib.sha256(header).hexdigest(),
        "version": version,
        "vab_id": vab_id,
        "declared_size": declared_size,
        "reserved": reserved,
        "programs": programs,
        "tones": tones,
        "vags": vags,
        "master_volume": master_volume,
        "master_pan": master_pan,
        "bank_attr": bank_attr,
        "attr2": attr2,
        "scope": "header_only_not_a_VB_bounds_or_sample_validation",
    }
    # The 128-entry program table is fixed-size, even when fewer programs
    # are populated. Only report it if the complete table is available.
    with path.open("rb") as f:
        f.seek(HEADER_SIZE)
        table = f.read(128 * 16)
    if len(table) == 128 * 16:
        used = []
        for index in range(128):
            record = table[index * 16:(index + 1) * 16]
            ntones = record[0]
            if ntones > 16:
                raise ValueError(f"program {index} exceeds 16 tones")
            if ntones:
                used.append({"program": index, "tones": ntones,
                             "volume": record[1], "pan": record[4]})
        result["program_table_complete"] = True
        result["populated_programs"] = used
        result["packed_tone_blocks_bytes"] = len(used) * 16 * 32
    else:
        result["program_table_complete"] = False
    return result

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vh", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_vab_header(args.vh), indent=2))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
