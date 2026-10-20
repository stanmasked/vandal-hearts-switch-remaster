#!/usr/bin/env python3
"""Verify syntax and conservative claims of a private MAP02 digest-only receipt.

No original BIN or sector bytes are accepted, opened, or published. This
checks self-reported fields, NOT the hashes against the user's physical disc.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat

SCHEMA = "vh.map02.local-ru-disc-digest.v1"
MAX_BYTES = 4096
RAW_BYTES = 664849248
SECTOR_BYTES = 2352
MAP02_LBA = 0x1BCC
MAP02_SECTORS = 12
MAP02_PRS_BYTES = 22783
MAP02_PRS_SHA256 = "c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387"
FIELDS = frozenset((
    "schema", "raw_image_bytes", "raw_image_sectors", "raw_image_sha256",
    "cue_single_mode2_2352", "checked_xa_form1_sectors", "map02_prs_lba",
    "map02_prs_sectors", "map02_prs_bytes", "map02_prs_sha256",
    "map02_matches_prior_ru_audit", "byte_exact_original_us_executable_proven",
    "real_gameplay_capture_proven", "physical_ps1_pixel_parity_proven",
    "game_bytes_in_receipt",
))
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _unique(items):
    record = {}
    for name, value in items:
        if name in record:
            raise ValueError("duplicate JSON key")
        record[name] = value
    return record


def _reject_constant(_):
    raise ValueError("non-finite JSON number")


def validate_receipt(raw):
    """Fail closed on unknown fields, overclaims and inconsistent digests."""
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES
            or not raw.endswith(b"\n") or b"\r" in raw or b"\x00" in raw):
        raise ValueError("invalid receipt byte framing")
    try:
        record = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                            parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid receipt JSON") from exc
    if type(record) is not dict or record.keys() != FIELDS:
        raise ValueError("missing or unrecognized receipt fields")
    expected_numbers = {
        "raw_image_bytes": RAW_BYTES,
        "raw_image_sectors": RAW_BYTES // SECTOR_BYTES,
        "checked_xa_form1_sectors": 1 + MAP02_SECTORS,
        "map02_prs_lba": MAP02_LBA,
        "map02_prs_sectors": MAP02_SECTORS,
        "map02_prs_bytes": MAP02_PRS_BYTES,
    }
    for key, value in expected_numbers.items():
        if type(record[key]) is not int or record[key] != value:
            raise ValueError("unexpected receipt sector layout: " + key)
    exact = {
        "schema": SCHEMA,
        "cue_single_mode2_2352": True,
        "map02_prs_sha256": MAP02_PRS_SHA256,
        "map02_matches_prior_ru_audit": True,
        "byte_exact_original_us_executable_proven": False,
        "real_gameplay_capture_proven": False,
        "physical_ps1_pixel_parity_proven": False,
        "game_bytes_in_receipt": False,
    }
    for key, value in exact.items():
        if type(record[key]) is not type(value) or record[key] != value:
            raise ValueError("unsupported or overstated receipt: " + key)
    if (type(record["raw_image_sha256"]) is not str or
            _HEX64.fullmatch(record["raw_image_sha256"]) is None):
        raise ValueError("invalid whole-disc SHA-256")
    return {
        "receipt_schema_verified": True,
        "disc_layout_claim_consistent": True,
        "prior_map02_prs_digest_claim_consistent": True,
        "reported_raw_image_sha256": record["raw_image_sha256"],
        "raw_game_data_read": False,
        "self_reported_disc_bytes_independently_verified": False,
        "actual_gameplay_frame_verified": False,
        "physical_ps1_equivalence_proven": False,
    }


def verify_receipt_file(path):
    """Require a stable owner-private, no-follow JSON file only."""
    path = Path(path).absolute()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(path, flags)
    try:
        first = os.fstat(fd)
        if (not stat.S_ISREG(first.st_mode) or first.st_uid != os.geteuid()
                or stat.S_IMODE(first.st_mode) != 0o600
                or first.st_nlink != 1 or not 0 < first.st_size <= MAX_BYTES):
            raise ValueError("receipt must be an owner-private regular file")
        contents = os.read(fd, MAX_BYTES + 1)
        second = os.fstat(fd)
        current = path.lstat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if (any(getattr(first, key) != getattr(second, key) or
                getattr(first, key) != getattr(current, key) for key in fields)
                or not stat.S_ISREG(current.st_mode)):
            raise ValueError("receipt changed during read")
        return validate_receipt(contents)
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("private_digest_json", type=Path)
    args = parser.parse_args()
    try:
        result = verify_receipt_file(args.private_digest_json)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
