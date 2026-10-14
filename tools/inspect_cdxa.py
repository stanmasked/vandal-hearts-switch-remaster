#!/usr/bin/env python3
"""Inspect raw 2352-byte PlayStation CD sectors for CD-XA audio metadata."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

SECTOR_SIZE = 2352
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"
MODE_OFFSET = 15
SUBHEADER_OFFSET = 16


def inspect_raw_cd(path: Path) -> dict[str, object]:
    size = path.stat().st_size
    if size == 0:
        raise ValueError("Input file is empty.")
    if size % SECTOR_SIZE:
        raise ValueError(f"Input size {size} is not divisible by {SECTOR_SIZE}; expected raw 2352-byte sectors.")

    sectors = mode2 = sync_ok = duplicate_ok = xa_audio = form2_audio = 0
    submodes: Counter[int] = Counter()
    coding: Counter[int] = Counter()
    with path.open("rb") as stream:
        while sector := stream.read(SECTOR_SIZE):
            sectors += 1
            if sector[:12] == SYNC:
                sync_ok += 1
            if sector[MODE_OFFSET] != 2:
                continue
            mode2 += 1
            first = sector[SUBHEADER_OFFSET:SUBHEADER_OFFSET + 4]
            second = sector[SUBHEADER_OFFSET + 4:SUBHEADER_OFFSET + 8]
            if first != second:
                continue
            duplicate_ok += 1
            file_no, channel, submode, coding_info = first
            submodes[submode] += 1
            if submode & 0x04:
                xa_audio += 1
                coding[coding_info] += 1
                if submode & 0x20:
                    form2_audio += 1

    return {
        "sectors": sectors,
        "sync_ok": sync_ok,
        "mode2": mode2,
        "duplicate_subheaders": duplicate_ok,
        "xa_audio": xa_audio,
        "form2_audio": form2_audio,
        "submodes": dict(sorted(submodes.items())),
        "coding_info": dict(sorted(coding.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="raw BIN or extracted raw-sector stream (2352 bytes/sector)")
    args = parser.parse_args()
    if not args.input.is_file():
        parser.error(f"Input file not found: {args.input}")
    try:
        report = inspect_raw_cd(args.input)
    except ValueError as error:
        parser.error(str(error))
    print(f"File: {args.input}")
    for key in ("sectors", "sync_ok", "mode2", "duplicate_subheaders", "xa_audio", "form2_audio"):
        print(f"{key.replace('_', ' ')}: {report[key]}")
    print("submode counts:", ", ".join(f"0x{k:02X}={v}" for k, v in report["submodes"].items()) or "none")
    print("coding-info counts:", ", ".join(f"0x{k:02X}={v}" for k, v in report["coding_info"].items()) or "none")
    print("Note: this reports sector metadata only; it does not decode audio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
