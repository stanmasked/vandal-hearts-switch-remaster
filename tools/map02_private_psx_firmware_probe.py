#!/usr/bin/env python3
"""Owner-local PSX firmware *metadata* comparison for the private USA BK2.

This verifies that candidate BIOS *bytes* have the SHA-1 recorded by BizHawk
in a PSX_Firmware_* BK2 header field. It does NOT show which BIOS or core a
later EmuHawk replay actually loaded. Never print paths, hashes or media.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

from tools.inspect_map02_private_bk2 import parse_header, read_small, safe_members
from tools.map02_private_disc_movie_preflight import (
    _assert_stable, _open_stable, _resolve_private_file,
)

SCHEMA = "vh.map02.private-psx-firmware-header-comparison.v1"
MAX_BK2_FILE_BYTES = 8 * 1024 * 1024
MAX_BIOS_FILE_BYTES = 4 * 1024 * 1024
HASH_BLOCK_BYTES = 1024 * 1024
PSX_FIRMWARE_FIELD = re.compile(r"PSX_Firmware_[A-Za-z0-9_]{1,48}\Z")
SHA1 = re.compile(r"[0-9A-Fa-f]{40}\Z")


def _firmware_sha1_from_movie(private_bk2: Path) -> tuple[str | None, int]:
    """Read bounded BK2 metadata; keep all firmware SHA-1 values private."""
    source = _resolve_private_file(private_bk2)
    fd, before = _open_stable(source)
    try:
        if not 0 < before.st_size <= MAX_BK2_FILE_BYTES:
            raise ValueError("BK2 size is outside private comparison bounds")
        with os.fdopen(fd, "rb", closefd=False) as reader:
            with zipfile.ZipFile(reader) as movie:
                safe_members(movie)
                header = parse_header(read_small(movie, "Header.txt"))
            _assert_stable(fd, source, before)
    finally:
        os.close(fd)

    matches = []
    for key, value in header.items():
        if key.startswith("PSX_Firmware_"):
            if not PSX_FIRMWARE_FIELD.fullmatch(key) or not SHA1.fullmatch(value):
                raise ValueError("malformed PSX firmware header identity")
            matches.append(value.lower())
    # Multiple independent PSX firmware devices may legitimately exist.
    # A single BIOS candidate cannot authenticate all of them, so do not
    # infer which was used: mark the report ambiguous instead.
    if len(matches) > 8:
        raise ValueError("unexpected PSX firmware header entry count")
    unique = set(matches)
    if len(unique) != 1:
        return None, len(matches)
    return matches[0], len(matches)


def _candidate_bios_sha1(private_bios: Path) -> str:
    """Stream a private BIOS, with stable fd/path checking, without logs."""
    source = _resolve_private_file(private_bios)
    fd, before = _open_stable(source)
    try:
        if not 0 < before.st_size <= MAX_BIOS_FILE_BYTES:
            raise ValueError("private BIOS candidate is outside bounded size")
        digest = hashlib.sha1()  # BizHawk PSX_Firmware_* movie header uses SHA-1.
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(HASH_BLOCK_BYTES, remaining))
            if not chunk:
                raise ValueError("private BIOS candidate changed during read")
            digest.update(chunk)
            remaining -= len(chunk)
        _assert_stable(fd, source, before)
        return digest.hexdigest()
    finally:
        os.close(fd)


def compare_firmware(private_bk2: Path, private_bios: Path) -> dict:
    """Return aggregate only; NEVER identify the candidate file or digest."""
    expected, entries = _firmware_sha1_from_movie(private_bk2)
    actual = _candidate_bios_sha1(private_bios)
    comparable = expected is not None
    return {
        "schema": SCHEMA,
        "psx_firmware_header_fields_present": entries > 0,
        "psx_firmware_header_entry_count": entries,
        "single_unambiguous_psx_firmware_hash_available": comparable,
        "candidate_bios_sha1_matches_movie_psx_firmware_metadata": (
            comparable and actual == expected
        ),
        "actual_emuhawk_loaded_bios_authenticated": False,
        "active_psx_core_authenticated": False,
        "source_disc_or_bk2_playback_authenticated": False,
        "firmware_or_private_paths_or_hashes_published": False,
        "private_assets_uploaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner_private_bk2", type=Path)
    parser.add_argument("owner_private_psx_bios_candidate", type=Path)
    arguments = parser.parse_args()
    try:
        result = compare_firmware(
            arguments.owner_private_bk2, arguments.owner_private_psx_bios_candidate,
        )
    except (OSError, ValueError, TypeError, zipfile.BadZipFile, RuntimeError):
        parser.error("private PSX firmware metadata comparison failed")
    print(json.dumps(result, sort_keys=True, indent=2))
    # A missing/mismatched firmware header is unresolved, not authenticated.
    return 0 if result["candidate_bios_sha1_matches_movie_psx_firmware_metadata"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
