#!/usr/bin/env python3
"""Strict structural and homebrew-metadata check for an actual Switch NRO.

Validates NRO0, loader segments, MOD0 and optional ASET/NACP. This catches
packaging corruption before physical-console tests; it CANNOT establish
that an NRO boots on a real Switch. Source format reference: switchbrew
NRO0 and libnx include/switch/nro.h, with 0x10-byte NroStart.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ALIGN = 0x1000
HEADER = 0x80
ASET_HEADER = 0x38
EXPECTED_TITLE = "Vandal Hearts Switch Prototype"
EXPECTED_AUTHOR = "Vandal Hearts Switch Remaster contributors"


class NroError(ValueError):
    pass


def u32(data: bytes, offset: int) -> int:
    if offset + 4 > len(data):
        raise NroError("truncated NRO header")
    return struct.unpack_from("<I", data, offset)[0]


def u64(data: bytes, offset: int) -> int:
    if offset + 8 > len(data):
        raise NroError("truncated ASET section header")
    return struct.unpack_from("<Q", data, offset)[0]


def parse_nro(data: bytes) -> dict:
    if len(data) < HEADER:
        raise NroError("truncated NRO0 header")
    if data[0x10:0x14] != b"NRO0":
        raise NroError("missing NRO0 signature")
    nro_size = u32(data, 0x18)
    if nro_size < ALIGN or nro_size > len(data):
        raise NroError("invalid declared executable size")
    if nro_size % ALIGN:
        raise NroError("executable image must be page aligned")
    if u32(data, 0x14) != 0:
        raise NroError("unexpected NRO0 version")
    if u32(data, 0x1C) != 0:
        raise NroError("unsupported NRO0 flags in this candidate")
    segments = []
    cursor = 0
    for name, offset in (("text", 0x20), ("rodata", 0x28), ("data", 0x30)):
        start = u32(data, offset)
        length = u32(data, offset + 4)
        if start != cursor:
            raise NroError(f"{name} is not contiguous with prior segment")
        if length == 0 or length % ALIGN:
            raise NroError(f"{name} size must be a nonzero aligned page count")
        end = start + length
        if end > nro_size:
            raise NroError(f"{name} extends past executable size")
        segments.append({"name": name, "offset": start, "size": length})
        cursor = end
    if cursor != nro_size:
        raise NroError("segment sizes do not cover executable image")
    modoff = u32(data, 0x04)
    if modoff < HEADER or modoff + 4 > segments[0]["size"]:
        raise NroError("MOD0 offset is outside executable text")
    if data[modoff:modoff + 4] != b"MOD0":
        raise NroError("NroStart does not reference a MOD0 header")
    bss = u32(data, 0x38)
    if bss % ALIGN:
        raise NroError("bss is not page aligned")

    trailing = len(data) - nro_size
    if trailing == 0:
        raise NroError("missing homebrew ASET/NACP metadata")
    if trailing < ASET_HEADER or data[nro_size:nro_size + 4] != b"ASET":
        raise NroError("missing ASET header after executable")
    if u32(data, nro_size + 4) != 0:
        raise NroError("unsupported ASET version")

    occupied = []
    assets = {}
    for name, offset in (("icon", 0x8), ("nacp", 0x18), ("romfs", 0x28)):
        off = u64(data, nro_size + offset)
        length = u64(data, nro_size + offset + 8)
        if length == 0:
            # Reject dangling relative pointers for zero-length entries.
            if off != 0:
                raise NroError(f"empty {name} declares a nonzero offset")
            assets[name] = {"offset": 0, "size": 0}
            continue
        if off < ASET_HEADER or off > trailing or length > trailing - off:
            raise NroError(f"{name} points outside the homebrew assets")
        occupied.append((off, off + length, name))
        assets[name] = {"offset": off, "size": length}
    for left, right in zip(sorted(occupied), sorted(occupied)[1:]):
        if left[1] > right[0]:
            raise NroError("overlapping ASET asset sections")
    nacp = assets["nacp"]
    if nacp["size"] != 0x4000:
        raise NroError("missing full-size 0x4000-byte NACP metadata")
    # Candidate intentionally packages no icon or ROMFS/retail resources.
    if assets["romfs"]["size"] or assets["icon"]["size"]:
        raise NroError("unexpected embedded icon/ROMFS in asset-free candidate")
    nacp_start = nro_size + nacp["offset"]
    metadata = data[nacp_start:nacp_start + nacp["size"]]
    title = metadata[:0x200].split(b"\x00", 1)[0].decode("utf-8", "strict")
    author = metadata[0x200:0x300].split(b"\x00", 1)[0].decode("utf-8", "strict")
    if title != EXPECTED_TITLE:
        raise NroError("unexpected NACP application title")
    if author != EXPECTED_AUTHOR:
        raise NroError("unexpected NACP author")
    return {
        "format": "NRO0",
        "declared_executable_size": nro_size,
        "file_size": len(data),
        "mod0_offset": modoff,
        "bss_size": bss,
        "segments": segments,
        "assets": assets,
        "title": title,
        "author": author,
        "physical_switch_boot_verified": False,
        "retail_game_data_reconstructed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nro", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.nro.is_symlink() or not args.nro.is_file():
            raise NroError("input must be regular NRO file, not a symlink")
        result = parse_nro(args.nro.read_bytes())
        if args.report.is_symlink():
            raise NroError("report output must not be a symlink")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        print("VH_MAP02_HARDWARE_FORMAT_PASS nro0=1 three_segments=1 "
              "mod0=1 nacp=1 asset_free=1 real_console_test=0", flush=True)
    except (OSError, UnicodeError, NroError) as exc:
        print("VH_MAP02_HARDWARE_FORMAT_FAIL: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
