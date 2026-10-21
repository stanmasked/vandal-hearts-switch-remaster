#!/usr/bin/env python3
"""Owner-local audit of two manually exported *runtime* BizHawk core witnesses.

The optional BizHawk External Tool reads its live injected IEmulator;
the earlier Lua config check only reads preferred cores. These local receipts
are unauthenticated text, NOT cryptographic proof that a specific owner disc,
BIOS or BK2 was used, or that either receipt belongs to a PNG capture.
No original assets, absolute paths, fingerprints or process IDs are printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _open_stable, _resolve_private_file,
)

SCHEMA = "vh.map02.private-runtime-core-witness-review.v1"
MAGIC = "VH_MAP02_RUNTIME_CORE_WITNESS_V1"
MAX_RECEIPT_BYTES = 512
MAX_FRAME_COUNT = 2_000_000
MIN_WINDOWS_UTC_TICKS = 621355968000000000  # 1970-01-01 UTC
MAX_WINDOWS_UTC_TICKS = 725811840000000000  # 2300-01-01 UTC
KEYS = (
    "system",
    "loaded_core",
    "core_source",
    "process_id",
    "process_start_utc_ticks",
    "frame_count",
    "bios",
    "disc",
    "movie_sync",
)
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z")


def _decimal(value: str, *, maximum: int, minimum: int = 0) -> int:
    if not DECIMAL.fullmatch(value) or len(value) > 22:
        raise ValueError("malformed private core witness numeric field")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError("private core witness numeric field out of bounds")
    return number


def read_witness(source: Path) -> tuple[int, int, int]:
    """Verify strict little textual witness; keep process IDs local."""
    path = _resolve_private_file(source)
    fd, before = _open_stable(path)
    try:
        if not 0 < before.st_size <= MAX_RECEIPT_BYTES:
            raise ValueError("private core witness outside bounded size")
        chunks = []
        remaining = before.st_size
        while remaining:
            block = os.read(fd, remaining)
            if not block:
                raise ValueError("incomplete private core witness")
            chunks.append(block)
            remaining -= len(block)
        _assert_stable(fd, path, before)
    finally:
        os.close(fd)
    try:
        data = b"".join(chunks).decode("ascii")
    except UnicodeDecodeError:
        raise ValueError("private core witness must be strict ASCII") from None
    if not data.endswith("\n") or "\r" in data:
        raise ValueError("private core witness must use complete LF-only lines")
    lines = data.splitlines()
    if len(lines) != 1 + len(KEYS) or lines[0] != MAGIC:
        raise ValueError("private core witness schema or field count mismatch")
    fields = {}
    for line, key in zip(lines[1:], KEYS):
        prefix = key + "="
        if not line.startswith(prefix):
            raise ValueError("private core witness unexpected or misordered field")
        fields[key] = line[len(prefix):]
    for key, expected in (
        ("system", "PSX"),
        ("loaded_core", "Octoshock"),
        ("core_source", "IEmulator.Attributes.CoreName"),
        ("bios", "unverified"),
        ("disc", "unverified"),
        ("movie_sync", "unverified"),
    ):
        if fields[key] != expected:
            raise ValueError("private core witness has unsupported evidence claim")
    return (
        _decimal(fields["process_id"], maximum=2_147_483_647, minimum=1),
        _decimal(fields["process_start_utc_ticks"],
                 maximum=MAX_WINDOWS_UTC_TICKS,
                 minimum=MIN_WINDOWS_UTC_TICKS),
        _decimal(fields["frame_count"], maximum=MAX_FRAME_COUNT),
    )


def compare_witnesses(first: Path, second: Path) -> dict:
    """Report limited evidence only; distinct processes, not linked gameplay."""
    if Path(first) == Path(second):
        raise ValueError("two independent private witness paths are required")
    a = read_witness(first)
    b = read_witness(second)
    if a[:2] == b[:2]:
        raise ValueError("two private witnesses report the same emulator process")
    return {
        "schema": SCHEMA,
        "runtime_iemulator_core_witnesses_read": 2,
        "both_witnesses_report_psx_octoshock": True,
        "reported_emuhawk_process_identities_distinct": True,
        "process_or_witness_origin_cryptographically_authenticated": False,
        "witnesses_tied_to_specific_bk2_or_png_capture": False,
        "actual_loaded_bios_authenticated": False,
        "mounted_ps1_disc_authenticated": False,
        "original_map02_scene_authenticated": False,
        "private_process_ids_paths_or_game_hashes_published": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first_owner_private_core_witness", type=Path)
    parser.add_argument("second_owner_private_core_witness", type=Path)
    args = parser.parse_args()
    try:
        result = compare_witnesses(
            args.first_owner_private_core_witness,
            args.second_owner_private_core_witness,
        )
    except (OSError, ValueError, TypeError, UnicodeError, RuntimeError):
        parser.error("private runtime IEmulator core witness audit rejected")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
