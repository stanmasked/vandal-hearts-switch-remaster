#!/usr/bin/env python3
"""Verify a GitHub-hosted MAP02 receipt artifact against a separate SHA-256.

The expected SHA-256 MUST arrive through a channel other than the JSON
being verified (e.g. a producing job output). This is not a signature or
an attestation by a trust authority outside GitHub Actions.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from tools import run_map02_sealed_gpu_receipt_chain as chain

MAX_REPORT_BYTES = 1024 * 1024


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("MAP02 published report contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("MAP02 published report contains non-finite JSON")


def verify_published(path, expected_sha256):
    """Revalidate a published report, requiring a separately supplied hash."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("MAP02 expected external SHA-256 is missing or malformed")
    file = Path(path)
    if file.is_symlink():
        raise ValueError("MAP02 published report cannot be a symlink")
    fd = os.open(file, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                not 0 < before.st_size <= MAX_REPORT_BYTES):
            raise ValueError("MAP02 published report is not a bounded regular file")
        raw = os.read(fd, MAX_REPORT_BYTES + 1)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or
                (before.st_dev, before.st_ino, before.st_size,
                 before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_size,
                 after.st_mtime_ns, after.st_ctime_ns)):
            raise ValueError("MAP02 published report changed during reading")
    finally:
        os.close(fd)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise ValueError("MAP02 published report SHA-256 differs from job commitment")
    try:
        bundle = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("MAP02 published report JSON malformed") from exc
    if not isinstance(bundle, dict) or bundle.get("schema") != chain.SCHEMA:
        raise ValueError("MAP02 published report schema mismatch")
    if (bundle.get("sealed_receipt_snapshots") != 3 or
            bundle.get("receipt_chain_consistent") is not True or
            bundle.get("intermediate_receipt_files_written") is not False or
            bundle.get("externally_authenticated") is not False or
            bundle.get("hd_replacement_authorized") is not False):
        raise ValueError("MAP02 published report security flags invalid")
    receipts = bundle.get("receipt_sha256")
    if not isinstance(receipts, dict) or set(receipts) != {
            "primary", "linked", "inspection"}:
        raise ValueError("MAP02 published report receipt digest inventory invalid")
    for role in ("primary", "linked", "inspection"):
        section = bundle.get(role)
        if not isinstance(section, dict):
            raise ValueError("MAP02 published report receipt missing")
        if (not isinstance(receipts[role], str) or
                not re.fullmatch(r"[0-9a-f]{64}", receipts[role]) or
                hashlib.sha256(chain._canonical(section)).hexdigest() != receipts[role]):
            raise ValueError("MAP02 published report embedded receipt digest differs")
    chain._verify_chain(
        bundle["primary"], bundle["linked"], bundle["inspection"])
    return {
        "schema": "vh.map02.published-gpu-receipt-audit.v1",
        "published_report_sha256": actual,
        "caller_supplied_sha256_matched": True,
        "three_embedded_receipts_checked": 3,
        "receipt_chain_consistent": True,
        "independent_digital_signature_verified": False,
        "hd_replacement_authorized": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report")
    p.add_argument("--expected-sha256", required=True)
    args = p.parse_args()
    try:
        result = verify_published(args.report, args.expected_sha256)
    except (OSError, ValueError, UnicodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
