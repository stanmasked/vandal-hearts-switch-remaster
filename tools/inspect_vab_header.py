#!/usr/bin/env python3
"""Read-only structural inspection of the 32-byte Sony VAB VH header.

This validates complete program/tone metadata only; it never reads VB audio.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path

HEADER_SIZE = 32
PROGRAM_TABLE_SIZE = 128 * 16
TONE_BLOCK_SIZE = 16 * 32

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
        "scope": "VH_structural_metadata_only_not_a_VB_or_audio_decode",
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
        result["packed_tone_blocks_bytes"] = len(used) * TONE_BLOCK_SIZE
        result["tone_table_offset"] = HEADER_SIZE + PROGRAM_TABLE_SIZE
        result["vag_size_table_offset"] = (
            result["tone_table_offset"] + result["packed_tone_blocks_bytes"]
        )
        # A file may contain a header only or a partial transfer. Never
        # claim tone validation unless every packed 16-tone block is present.
        with path.open("rb") as f:
            f.seek(result["tone_table_offset"])
            raw_tones = f.read(result["packed_tone_blocks_bytes"])
        result["tone_table_complete"] = (
            len(raw_tones) == result["packed_tone_blocks_bytes"]
        )
        if result["tone_table_complete"]:
            for block_index, program in enumerate(used):
                program["block_index"] = block_index
                tones_in_use = []
                for tone_index in range(program["tones"]):
                    start = block_index * TONE_BLOCK_SIZE + tone_index * 32
                    record = raw_tones[start:start + 32]
                    low, high = record[6], record[7]
                    adsr1, adsr2, parent, vag = struct.unpack_from("<HHhh", record, 16)
                    if low > 127 or high > 127 or low > high:
                        raise ValueError(
                            f"program {program['program']} tone {tone_index}: invalid key range"
                        )
                    if parent != program["program"]:
                        raise ValueError(
                            f"program {program['program']} tone {tone_index}: wrong parent program"
                        )
                    if not 1 <= vag <= vags:
                        raise ValueError(
                            f"program {program['program']} tone {tone_index}: VAG index out of range"
                        )
                    tones_in_use.append({
                        "tone": tone_index, "vag": vag,
                        "key_min": low, "key_max": high,
                        "center": record[4], "fine_tune": record[5],
                        "volume": record[2], "pan": record[3],
                        "mode": record[1], "adsr1": adsr1, "adsr2": adsr2,
                    })
                program["active_tones"] = tones_in_use
            result["tone_table_sha256"] = hashlib.sha256(raw_tones).hexdigest()
    else:
        result["program_table_complete"] = False
        result["tone_table_complete"] = False
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
