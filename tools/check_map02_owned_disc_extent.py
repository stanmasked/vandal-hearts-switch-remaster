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
import stat

from tools.map02_local_capture_handoff import (
    SOURCE_BLOBS, verify_pinned_upstream,
)
from tools.prepare_map02_pcport import git_blob_sha1

SECTOR_RAW = 2352
USER_DATA_START = 24
USER_DATA_BYTES = 2048
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
    frames = lba + PREGAP
    if data[12:15] != bytes((
        _bcd(frames // (75 * 60)),
        _bcd(frames // 75 % 60),
        _bcd(frames % 75),
    )):
        raise ValueError("MAP02 raw CD sector MSF address mismatch")
    return data


def _disc_file_identity(info):
    """One private raw-image inode, including mutation-sensitive metadata."""
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _whole_disc_sha256(fd, length):
    digest = hashlib.sha256()
    for offset in range(0, length, 1 << 20):
        count = min(1 << 20, length - offset)
        data = os.pread(fd, count, offset)
        if len(data) != count:
            raise ValueError("owned MAP02 raw disc short read during hashing")
        digest.update(data)
    return digest.hexdigest()



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
    try:
        fd = os.open(image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError:
        raise ValueError("owned MAP02 raw image input unavailable") from None
    try:
        original = os.fstat(fd)
        if not stat.S_ISREG(original.st_mode) or original.st_size <= 0:
            raise ValueError("capture input is not a nonempty regular file")
        if original.st_uid != os.geteuid() or original.st_mode & 0o077:
            raise ValueError("owned game-image input must be owner-private")
        if original.st_nlink != 1:
            raise ValueError("owned MAP02 raw disc must have exactly one hardlink")
        planned = _disc_file_identity(original)
        if _disc_file_identity(os.stat(image, follow_symlinks=False)) != planned:
            raise ValueError("owned MAP02 raw disc pathname changed before hashing")
        size = original.st_size
        if size % SECTOR_RAW or size < (lba + count) * SECTOR_RAW:
            raise ValueError("original raw CD image size/extent incomplete")
        # Both full hashes and all sector reads use the very SAME descriptor.
        # Reopening the pathname here would allow a between-checks swap.
        image_hash = _whole_disc_sha256(fd, size)
        if _disc_file_identity(os.fstat(fd)) != planned:
            raise ValueError("owned MAP02 raw disc changed during first hash")
        boot = _raw_sector(fd, BOOT_LBA_US)
        if boot[USER_DATA_START:USER_DATA_START + 8] != b"PS-X EXE":
            raise ValueError("original US PS-X EXE boot signature absent")
        digest = hashlib.sha256()
        for sector in range(lba, lba + count):
            raw = _raw_sector(fd, sector)
            digest.update(raw[USER_DATA_START:
                              USER_DATA_START + USER_DATA_BYTES])
        if _disc_file_identity(os.fstat(fd)) != planned:
            raise ValueError("owned MAP02 raw disc changed during sector read")
        if _whole_disc_sha256(fd, size) != image_hash:
            raise ValueError("owned game image changed while reading MAP02 sectors")
        if (_disc_file_identity(os.fstat(fd)) != planned or
                _disc_file_identity(os.stat(image, follow_symlinks=False))
                != planned):
            raise ValueError("owned MAP02 raw disc pathname or inode changed during audit")
    except OSError:
        raise ValueError("owned MAP02 raw image verification unavailable") from None
    finally:
        os.close(fd)
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
