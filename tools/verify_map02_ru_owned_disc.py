#!/usr/bin/env python3
"""Privately re-read the owned RU PS1 image and verify its MAP02 source bytes.

Reuses the existing original-format MODE2/Form1+EDC reader and PRS decoder.
No extracted assets, executable bytes, filesystem paths or render captures
are emitted. This proves the local disc's byte identity to a pinned source;
it does NOT establish which disc a separate PC executable opened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from tools.audit_map02_disc_prs import (
    START_SECTOR, SECTOR_COUNT, DAT_START_SECTOR, DAT_SECTOR_COUNT,
    PRIOR_DAT_LENGTH, read_sectors, audit_prs,
)
from tools.check_map02_ru_receipt import check_receipt, EXPECTED_HASHES
from tools.reconcile_map02_ru_runtime_trace import reconcile

EXPECTED_DISC_BYTES = 664849248
EXPECTED_DISC_SHA256 = (
    "48c686f9ae7e57615c06fd20d1048b2b8e9e7debabc371e6e941821b6b3b121a"
)
PRS_BYTES = 22783
CHUNK_BYTES = 1024 * 1024


def _readonly_disc_digest(path):
    """Hash the complete regular file through a no-follow file descriptor."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("source image must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    fd = os.open(str(path), flags)
    try:
        initial = os.fstat(fd)
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError("source image must be a regular file")
        if initial.st_size != EXPECTED_DISC_BYTES:
            raise ValueError("source image has unexpected length")
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb", closefd=False) as handle:
            while True:
                block = handle.read(CHUNK_BYTES)
                if not block:
                    break
                digest.update(block)
        final = os.fstat(fd)
        if (initial.st_dev, initial.st_ino, initial.st_size, initial.st_mtime_ns) != (
            final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns
        ):
            raise ValueError("source image changed during hashing")
        if digest.hexdigest() != EXPECTED_DISC_SHA256:
            raise ValueError("source image SHA-256 differs from the pinned RU image")
        return initial
    finally:
        os.close(fd)


def _unchanged(path, original):
    current = os.stat(path, follow_symlinks=False)
    if (not stat.S_ISREG(current.st_mode) or
            (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) !=
            (original.st_dev, original.st_ino, original.st_size, original.st_mtime_ns)):
        raise ValueError("source image changed during MAP02 verification")


def _validate_audit(result):
    """Check the existing decoder's calculated evidence, not just a receipt."""
    if type(result) is not dict:
        raise ValueError("MAP02 decoder did not return a report")
    for field in (
        "matches_prior_logical_compressed_sha256",
        "matches_prior_padded_compressed_sha256",
        "matches_prior_decompressed_sha256",
        "matches_prior_target_gfx",
    ):
        if result.get(field) is not True:
            raise ValueError("original MAP02 PRS evidence differs: " + field)
    if result.get("compressed_logical_sha256") != EXPECTED_HASHES["prs_logical"]:
        raise ValueError("incorrect PRS logical digest")
    if result.get("compressed_padded_sha256") != EXPECTED_HASHES["prs_file"]:
        raise ValueError("incorrect PRS file digest")
    if result.get("decompressed_sha256") != EXPECTED_HASHES["prs_unpacked"]:
        raise ValueError("incorrect decompressed MAP02 digest")
    if result.get("compressed_byte_count") != 22779 or result.get("logical_prs_byte_count") != PRS_BYTES:
        raise ValueError("incorrect MAP02 compressed file length")
    if result.get("available_bytes") != PRS_BYTES:
        raise ValueError("incorrect available MAP02 PRS length")
    dat = result.get("dat_comparison")
    if type(dat) is not dict:
        raise ValueError("missing independently decoded DAT comparison")
    for field in (
        "matches_prior_dat_sha256", "matches_prior_disc_audit",
        "matches_prior_disc_audit_with_provenance"
    ):
        if dat.get(field) is not True:
            raise ValueError("original MAP02 DAT evidence differs: " + field)
    if dat.get("dat_sha256") != EXPECTED_HASHES["dat_file"]:
        raise ValueError("incorrect MAP02 DAT digest")
    if dat.get("dat_byte_count") != PRIOR_DAT_LENGTH:
        raise ValueError("incorrect MAP02 DAT length")
    if dat.get("difference_count") != 2:
        raise ValueError("unexpected number of PRS/DAT differences")
    faces = dat.get("target_faces")
    if type(faces) is not list or len(faces) != 2:
        raise ValueError("missing map-face comparison evidence")
    expected = ((243, 241, 98), (319, 243, 150))
    for row, (record, prs, datgfx) in zip(faces, expected):
        if (type(row) is not dict or row.get("record_index") != record or
                row.get("prs_local_gfx") != prs or row.get("dat_local_gfx") != datgfx):
            raise ValueError("unexpected original MAP02 face mapping")
    return True


def verify_owned_ru_disc(disc_image, receipt_file, *, capture_directory=None):
    """Rehash the image, read/check its genuine sectors, then optionally replay a PC trace."""
    receipt_file = Path(receipt_file)
    if (receipt_file.is_symlink() or not receipt_file.is_file() or
            not 0 < receipt_file.stat().st_size <= 32768):
        raise ValueError("MAP02 receipt must be a bounded regular file")
    receipt_raw = receipt_file.read_bytes()
    check_receipt(json.loads(receipt_raw.decode("utf-8")))

    disc_image = Path(disc_image)
    first = _readonly_disc_digest(disc_image)
    # The CD reader verifies per-sector sync, mode and EDC on every requested sector.
    prs = read_sectors(disc_image, "mode2-2352", start_sector=START_SECTOR,
                       sector_count=SECTOR_COUNT)[:PRS_BYTES]
    dat = read_sectors(disc_image, "mode2-2352", start_sector=DAT_START_SECTOR,
                       sector_count=DAT_SECTOR_COUNT)[:PRIOR_DAT_LENGTH]
    checked = audit_prs(prs, dat=dat)
    _validate_audit(checked)
    _unchanged(disc_image, first)

    report = {
        "schema": "vh.map02.ru-owned-disc-gate.v1",
        "pinned_ru_disc_sha256_verified": True,
        "full_disc_bytes_read": EXPECTED_DISC_BYTES,
        "mode2_form1_edc_verified_sectors": SECTOR_COUNT + DAT_SECTOR_COUNT,
        "map02_prs_decode_sha256_verified": True,
        "map02_dat_sha256_verified": True,
        "map02_prs_dat_exact_differences": 2,
        "source_receipt_consistent": True,
        "source_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "pc_capture_present": capture_directory is not None,
        "same_owned_disc_used_by_executable_proven": False,
        "actual_gameplay_authenticated": False,
        "native_gpu_vram_pixels_verified": False,
    }
    if capture_directory is not None:
        joined = reconcile(receipt_file, capture_directory)
        report["pc_capture_stdout_replayed"] = joined["capture_stdout_independently_replayed"]
        report["pc_trace_consistent_variant"] = joined["pc_trace_consistent_variant"]
        report["pc_capture_report_sha256"] = joined["capture_report_sha256"]
        report["capture_executable_sha256"] = joined["capture_executable_sha256"]
        report["separate_map_loads_checked"] = joined["separate_map_loads_checked"]
    report["warning"] = (
        "Owned source bytes are verified locally, but the separate PC capture is "
        "not cryptographically bound to an executed CdRead or native GPU pixels."
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--disc-image", type=Path, required=True,
                        help="private user-owned RU v1.6 raw MODE2/2352 BIN")
    parser.add_argument("--receipt", type=Path, required=True,
                        help="private map02_ru_source_reconciliation.json")
    parser.add_argument("--capture", type=Path,
                        help="optional independent local full-trace PC capture directory")
    args = parser.parse_args()
    try:
        result = verify_owned_ru_disc(args.disc_image, args.receipt,
                                      capture_directory=args.capture)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
