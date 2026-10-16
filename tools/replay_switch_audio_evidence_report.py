#!/usr/bin/env python3
"""Stage 225: deterministic report receipt with repeated ZIP verification.

"record" independently re-audits the same ZIP twice and writes a stable,
exclusive-create JSON receipt. "replay" verifies externally pinned SHA-256
of both ZIP and receipt, rechecks the ZIP twice, and compares the complete
canonical semantic report. No console, SD, files under test or original ZIP
are modified. SHA-256 is NOT a digital signature.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import analyze_switch_audio_log as audio
import archive_switch_audio_handoff as archive
import compare_switch_audio_archive_reports as cross_host
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-repeatable-report/v1"
MAX_RECEIPT = 256 * 1024
RECEIPT_KEYS = {
    "schema", "hardware_status", "archive_sha256", "snapshot_sha256",
    "snapshot", "verification_passes", "manual_signoff",
}


class ReplayError(ValueError):
    """Reproducibility failure or an altered report/ZIP."""


def require(condition: bool, why: str) -> None:
    if not condition:
        raise ReplayError(why)


def canonical_bytes(value: dict) -> bytes:
    """Canonical for this defined JSON-only schema, without host/path metadata."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stable_snapshot(zip_path: Path, expected_zip_sha: str) -> dict:
    """Detect report drift and ZIP modification over two independent passes."""
    require(isinstance(expected_zip_sha, str) and
            archive.SHA_RE.fullmatch(expected_zip_sha) is not None,
            "expected ZIP hash must be 64 lowercase hexadecimal digits")
    require(zip_path.is_file() and not zip_path.is_symlink(),
            "input archive missing or symlinked")
    before = archive.digest(zip_path)
    require(before["sha256"] == expected_zip_sha and
            0 < before["size"] <= archive.MAX_ZIP,
            "ARCHIVE_CHANGED: input ZIP does not match independent SHA-256")
    first = cross_host.verified_snapshot(zip_path, expected_zip_sha)
    # Detect changes between passes even if a snapshot happened to parse.
    middle = archive.digest(zip_path)
    require(middle == before, "ARCHIVE_CHANGED_DURING_VERIFICATION")
    second = cross_host.verified_snapshot(zip_path, expected_zip_sha)
    after = archive.digest(zip_path)
    require(after == before, "ARCHIVE_CHANGED_DURING_VERIFICATION")
    require(canonical_bytes(first) == canonical_bytes(second),
            "NONDETERMINISTIC_EVIDENCE_REPORT: two independent audits differ")
    require(first["archive_sha256"] == expected_zip_sha and
            first["archive_bytes"] == before["size"] and
            first["hardware_status"] == bundle.HARDWARE_STATUS and
            first["manual_signoff"] == "REQUIRED_NOT_AUTOMATED",
            "repeated snapshot has invalid hardware or ZIP identity")
    return first


def receipt_for(zip_path: Path, expected_sha: str) -> dict:
    snapshot = stable_snapshot(zip_path, expected_sha)
    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "archive_sha256": expected_sha,
        "snapshot_sha256": sha256(canonical_bytes(snapshot)),
        "snapshot": snapshot,
        "verification_passes": 2,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def receipt_bytes(receipt: dict) -> bytes:
    """A reproducible byte representation with exactly one final LF."""
    return canonical_bytes(receipt) + b"\n"


def record(zip_path: Path, expected_sha: str, output: Path) -> dict:
    require(output.parent.is_dir(), "receipt output parent does not exist")
    require(not output.is_symlink() and not output.exists(),
            "receipt already exists; refusing overwrite")
    require(output.resolve() != zip_path.resolve(),
            "receipt output must not refer to input ZIP")
    receipt = receipt_for(zip_path, expected_sha)
    raw = receipt_bytes(receipt)
    require(len(raw) <= MAX_RECEIPT, "receipt too large")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        # Persist receipt to host storage; not a test of SD durability.
        import os
        os.fsync(stream.fileno())
    return {
        "result": "DETERMINISTIC_REPORT_RECEIPT_CREATED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "archive_sha256": expected_sha,
        "receipt_sha256": sha256(raw),
        "canonical_snapshot_sha256": receipt["snapshot_sha256"],
        "verification_passes": 2,
        "out_of_band_receipt_sha256_required": True,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def read_receipt(path: Path, pinned_sha256: str) -> dict:
    require(isinstance(pinned_sha256, str) and
            archive.SHA_RE.fullmatch(pinned_sha256) is not None,
            "expected receipt SHA-256 must be 64 lowercase hexadecimal digits")
    require(path.is_file() and not path.is_symlink(),
            "receipt missing or a symbolic link")
    require(path.stat().st_size <= MAX_RECEIPT,
            "receipt exceeds 256 KiB")
    raw = path.read_bytes()
    require(sha256(raw) == pinned_sha256,
            "RECEIPT_SHA256_MISMATCH: receipt has changed since original recording")
    try:
        receipt = json.loads(raw.decode("utf-8"),
                             object_pairs_hook=bundle.unique_pairs,
                             parse_constant=lambda x: (_ for _ in ()).throw(
                                 ReplayError("invalid non-finite JSON constant")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReplayError(f"invalid receipt JSON: {exc}") from exc
    require(isinstance(receipt, dict) and set(receipt) == RECEIPT_KEYS and
            receipt["schema"] == SCHEMA and
            receipt["hardware_status"] == bundle.HARDWARE_STATUS and
            receipt["manual_signoff"] == "REQUIRED_NOT_AUTOMATED" and
            type(receipt["verification_passes"]) is int and
            receipt["verification_passes"] == 2,
            "invalid receipt schema, replay count or claimed hardware PASS")
    require(receipt_bytes(receipt) == raw,
            "NONCANONICAL_RECEIPT: receipt encoding differs from pinned canonical bytes")
    archive_hash = receipt["archive_sha256"]
    snapshot_hash = receipt["snapshot_sha256"]
    require(isinstance(archive_hash, str) and
            archive.SHA_RE.fullmatch(archive_hash) is not None and
            isinstance(snapshot_hash, str) and
            archive.SHA_RE.fullmatch(snapshot_hash) is not None and
            isinstance(receipt["snapshot"], dict) and
            receipt["snapshot"].get("schema") == cross_host.SCHEMA and
            receipt["snapshot"].get("hardware_status") == bundle.HARDWARE_STATUS and
            receipt["snapshot"].get("manual_signoff") == "REQUIRED_NOT_AUTOMATED",
            "invalid receipt archive or snapshot identity")
    require(sha256(canonical_bytes(receipt["snapshot"])) == snapshot_hash,
            "SNAPSHOT_SHA256_MISMATCH: receipt inner report altered")
    return receipt


def replay(zip_path: Path, expected_zip_sha: str,
           receipt_path: Path, expected_receipt_sha: str) -> dict:
    """Re-check pinned receipt and two fresh audits of the original ZIP."""
    receipt = read_receipt(receipt_path, expected_receipt_sha)
    require(receipt["archive_sha256"] == expected_zip_sha,
            "RECEIPT_REFERENCES_DIFFERENT_ARCHIVE")
    snapshot = stable_snapshot(zip_path, expected_zip_sha)
    current_sha = sha256(canonical_bytes(snapshot))
    require(current_sha == receipt["snapshot_sha256"] and
            snapshot == receipt["snapshot"],
            "REPORT_DRIFT: current validated ZIP yields different audit data")
    return {
        "result": "PINNED_REPORT_REPRODUCED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "archive_sha256": expected_zip_sha,
        "receipt_sha256": expected_receipt_sha,
        "canonical_snapshot_sha256": current_sha,
        "verification_passes": 2,
        "report_was_unchanged": True,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "limitations": (
            "Two consistent local audits and SHA-256 pinning do not sign the "
            "archive, certify an independent operator, physical Switch audio, "
            "SD durability or the truth of recorded hardware observations. "
            "The receipt SHA-256 must be preserved independently of the ZIP."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("record", help="write stable pinned audit receipt")
    create.add_argument("archive", type=Path)
    create.add_argument("--expected-archive-sha256", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("replay", help="repeat original audit and check receipt")
    check.add_argument("archive", type=Path)
    check.add_argument("--expected-archive-sha256", required=True)
    check.add_argument("--receipt", type=Path, required=True)
    check.add_argument("--expected-receipt-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "record":
            result = record(args.archive, args.expected_archive_sha256, args.output)
        else:
            result = replay(args.archive, args.expected_archive_sha256,
                            args.receipt, args.expected_receipt_sha256)
    except (ReplayError, cross_host.ComparisonError, archive.ArchiveError,
            handoff.HandoffError, operator.OperatorError, bundle.BundleError,
            audio.LogFormatError, OSError, TypeError, KeyError,
            ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
