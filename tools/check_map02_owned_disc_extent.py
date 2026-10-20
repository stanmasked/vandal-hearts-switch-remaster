#!/usr/bin/env python3
"""Privately audit the US MAP02 CD resource extent in an owned raw BIN image.

Compare the layout with the EXACT pinned original source CDF_M_MAP02_PRS
table entry, then check 12 raw 2352-byte sectors for PSX sector sync and
BCD MSF addresses; hash only their 2048-byte data fields. No game bytes
are persisted or displayed. A valid digest does NOT prove this code path
was ever reached by the running game, nor PS1 hardware equivalence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from tools.map02_local_capture_handoff import (
    SOURCE_BLOBS, _sha_file, verify_pinned_upstream,
)
from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_disc_prs import xa_edc

SECTOR_RAW = 2352
USER_DATA_START = 24
USER_DATA_BYTES = 2048
XA_EDC_OFFSET = 0x818
PREGAP = 150
BOOT_LBA_US = 23
RESOURCE = "CDF_M_MAP02_PRS"
LAYOUT = re.compile(
    r"\[\s*CDF_M_MAP02_PRS\s*\]\s*=\s*"
    r"\{\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,"
    r"\s*gScratch1_801317c0\s*\}"
)


def extract_layout(source):
    matches = LAYOUT.findall(source)
    if len(matches) != 1:
        raise ValueError("original MAP02 CD resource table anchor missing/ambiguous")
    lba, count = [int(n, 16) for n in matches[0]]
    if (lba, count) != (0x1bcc, 0x0c):
        raise ValueError("unexpected original MAP02 CD resource LBA/count")
    return lba, count


def _bcd(number):
    return ((number // 10) << 4) | (number % 10)


def _raw_sector(fd, lba):
    data = os.pread(fd, SECTOR_RAW, lba * SECTOR_RAW)
    if len(data) != SECTOR_RAW:
        raise ValueError("MAP02 raw CD sector incomplete")
    if data[:12] != b"\x00" + b"\xff" * 10 + b"\x00":
        raise ValueError("MAP02 raw CD sector synchronization mismatch")
    # A sync/MSF-valid sector may still be wrong-mode, truncated, or
    # corrupted. The original CD source expects Mode 2 Form 1 user data.
    # Check its duplicate XA subheader and recorded 32-bit EDC before
    # interpreting either the boot marker or any MAP02 resource bytes.
    if data[15] != 2:
        raise ValueError("MAP02 raw CD sector is not Mode 2")
    if data[16:20] != data[20:24]:
        raise ValueError("MAP02 raw CD sector XA subheaders disagree")
    if data[18] & 0x20:
        raise ValueError("MAP02 raw CD sector uses unsupported Form 2")
    stored_edc = int.from_bytes(data[XA_EDC_OFFSET:XA_EDC_OFFSET + 4], "little")
    actual_edc = xa_edc(data[0x10:XA_EDC_OFFSET])
    if stored_edc != actual_edc:
        raise ValueError("MAP02 raw CD sector Mode 2 Form 1 EDC mismatch")
    frames = lba + PREGAP
    if data[12:15] != bytes((
        _bcd(frames // (75 * 60)),
        _bcd(frames // 75 % 60),
        _bcd(frames % 75),
    )):
        raise ValueError("MAP02 raw CD sector MSF address mismatch")
    return data


def verify_map02_disc_extent(image, upstream):
    source_root = Path(upstream).absolute()
    pinned_identity = verify_pinned_upstream(source_root)
    path = source_root / "src/core/cd.c"
    if path.is_symlink():
        raise ValueError("original CD file table is a symlink")
    source_raw = path.read_bytes()
    if git_blob_sha1(source_raw) != SOURCE_BLOBS["src/core/cd.c"]:
        raise ValueError("original CD table no longer pinned")
    lba, count = extract_layout(source_raw.decode("utf-8"))
    # Explicit single-region US source only; do not silently use this
    # LBA against unrelated Japanese/Asian disc layouts.
    image = Path(image).absolute()
    image_hash = _sha_file(image, private=True)
    fd = os.open(
        image, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0))
    try:
        size = os.fstat(fd).st_size
        if size % SECTOR_RAW or size < (lba + count) * SECTOR_RAW:
            raise ValueError("original raw CD image size/extent incomplete")
        boot = _raw_sector(fd, BOOT_LBA_US)
        if boot[USER_DATA_START:USER_DATA_START + 8] != b"PS-X EXE":
            raise ValueError("original US PS-X EXE boot signature absent")
        digest = hashlib.sha256()
        for sector in range(lba, lba + count):
            raw = _raw_sector(fd, sector)
            digest.update(raw[USER_DATA_START:
                              USER_DATA_START + USER_DATA_BYTES])
    finally:
        os.close(fd)
    if _sha_file(image, private=True) != image_hash:
        raise ValueError("owned game image changed while reading MAP02 sectors")
    return {
        "resource": RESOURCE,
        "original_pc_cd_table_sha256": hashlib.sha256(source_raw).hexdigest(),
        "pinned_pc_cd_sources_sha256": pinned_identity,
        "owned_raw_image_sha256": image_hash,
        "resource_lba": lba,
        "resource_sector_count": count,
        "resource_user_data_sha256": digest.hexdigest(),
        "resource_user_data_bytes_checked": count * USER_DATA_BYTES,
        "original_gameplay_resource_read_observed": False,
        "retail_image_authenticity_proven": False,
        "physical_ps1_equivalence_proven": False,
        "raw_game_data_emitted": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("owned_raw_game_bin", type=Path)
    p.add_argument("--upstream-checkout", required=True, type=Path)
    args = p.parse_args()
    try:
        result = verify_map02_disc_extent(args.owned_raw_game_bin,
                                          args.upstream_checkout)
    except (OSError, ValueError, UnicodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
