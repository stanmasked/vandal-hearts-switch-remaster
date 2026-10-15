#!/usr/bin/env python3
"""Read-only structural inspection of the 32-byte Sony VAB VH header.

This deliberately does not interpret program/tone tables or VB sample offsets.
"""
from __future__ import annotations
import argparse
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
    return {
        "format": "VAB VH",
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
