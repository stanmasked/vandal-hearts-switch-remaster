#!/usr/bin/env python3
"""Stage 226: append-only, externally pinned chain of Switch evidence receipts.

Append requires the independently pinned prior head SHA-256 AND count. Verify
requires the independently pinned final head AND count; both replay all original
ZIP/receipt pairs using stage 225. This catches missing, reordered, substituted
or repeated links IF the pinned head/count are securely retained out of band.

A hash chain is not a digital signature, not tamper-proof storage, and does not
attest an operator, sound or physical Nintendo Switch. Originals are read-only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

import analyze_switch_audio_log as audio
import archive_switch_audio_handoff as archive
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import compare_switch_audio_archive_reports as cross_host
import replay_switch_audio_evidence_report as replay
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-receipt-chain/v1"
GENESIS = "0" * 64
MAX_RECORDS = 64
MAX_RECORD_BYTES = 8 * 1024
INDEX_PATTERN = re.compile(r"[0-9]{6}\.json\Z")
PATH_PATTERN = re.compile(r"[A-Za-z0-9_.\-/]{1,512}\Z")
RECORD_KEYS = {
    "schema", "hardware_status", "sequence", "previous_record_sha256",
    "archive_path", "receipt_path", "archive_sha256", "receipt_sha256",
    "snapshot_sha256", "handoff_review", "manual_signoff",
}


class ChainError(ValueError):
    """Fail-closed chain, anchor or evidence error."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ChainError(why)


def stable_bytes(obj: dict) -> bytes:
    return replay.canonical_bytes(obj) + b"\n"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def anchor(value: object, name: str) -> str:
    require(isinstance(value, str) and archive.SHA_RE.fullmatch(value) is not None,
            f"{name} must be 64 lowercase hex characters")
    return value


def validate_path(root: Path, raw: object, suffix: str) -> Path:
    require(isinstance(raw, str) and
            PATH_PATTERN.fullmatch(raw) is not None and
            "\\" not in raw and ":" not in raw, "invalid stored evidence path")
    parts = raw.split("/")
    require(not raw.startswith("/") and len(parts) >= 1 and
            all(x not in ("", ".", "..") for x in parts) and
            raw.endswith(suffix) and not raw.startswith("chain/"),
            "unsafe archive or receipt path")
    current = root
    for part in parts:
        current = current / part
        require(not current.is_symlink(),
                "evidence path contains a symbolic link")
    require(current.resolve().is_relative_to(root.resolve()) and
            current.is_file(), "evidence file missing or outside storage root")
    return current


def get_chain_dir(storage: Path) -> tuple[Path, Path]:
    require(not storage.is_symlink() and storage.is_dir(),
            "storage root missing or symbolic link")
    root = storage.resolve()
    directory = root / "chain"
    require(directory.is_dir() and not directory.is_symlink(),
            "storage root must contain a non-symlink chain directory")
    return root, directory


def read_entry(path: Path) -> tuple[dict, str]:
    require(not path.is_symlink() and path.is_file(),
            "chain record missing or symbolic link")
    require(path.stat().st_size <= MAX_RECORD_BYTES,
            "chain record exceeds 8 KiB")
    raw = path.read_bytes()
    try:
        entry = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ChainError(f"invalid chain JSON: {exc}") from exc
    require(isinstance(entry, dict) and set(entry) == RECORD_KEYS and
            entry["schema"] == SCHEMA and
            entry["hardware_status"] == bundle.HARDWARE_STATUS and
            entry["manual_signoff"] == "REQUIRED_NOT_AUTOMATED",
            "unrecognized chain record or claimed hardware PASS")
    require(stable_bytes(entry) == raw,
            "NONCANONICAL_CHAIN_RECORD: chain file was changed or reformatted")
    require(type(entry["sequence"]) is int and
            1 <= entry["sequence"] <= MAX_RECORDS,
            "invalid chain sequence")
    for key in ("previous_record_sha256", "archive_sha256",
                "receipt_sha256", "snapshot_sha256"):
        anchor(entry[key], key)
    for key, ext in (("archive_path", ".zip"), ("receipt_path", ".json")):
        require(isinstance(entry[key], str) and
                PATH_PATTERN.fullmatch(entry[key]) is not None and
                entry[key].endswith(ext) and
                not entry[key].startswith("chain/"),
                "invalid chain evidence path")
    require(isinstance(entry["handoff_review"], str) and
            entry["handoff_review"] in ("INCONCLUSIVE", "INVESTIGATE",
                                       "READY_FOR_INDEPENDENT_MANUAL_REVIEW"),
            "invalid chain review status")
    return entry, sha256(raw)


def directory_entries(directory: Path) -> list[Path]:
    paths = sorted(directory.iterdir(), key=lambda p: p.name)
    require(len(paths) <= MAX_RECORDS, "chain exceeds 64 records")
    require(all(INDEX_PATTERN.fullmatch(p.name) is not None and
                p.is_file() and not p.is_symlink() for p in paths),
            "unexpected, missing or unsafe file in chain directory")
    names = [f"{i:06d}.json" for i in range(1, len(paths) + 1)]
    require([p.name for p in paths] == names,
            "CHAIN_GAP_OR_REORDER: missing numbered record or invalid order")
    return paths


def verify(storage: Path, expected_head: str, expected_count: int) -> dict:
    expected_head = anchor(expected_head, "expected chain head")
    require(type(expected_count) is int and 0 <= expected_count <= MAX_RECORDS,
            "expected count must be an integer from 0 to 64")
    root, directory = get_chain_dir(storage)
    paths = directory_entries(directory)
    require(len(paths) == expected_count,
            "CHAIN_COUNT_MISMATCH: chain is missing or has unexpected records")
    previous = GENESIS
    used_archives, used_receipts = set(), set()
    entries = []
    for sequence, path in enumerate(paths, 1):
        record, record_hash = read_entry(path)
        require(record["sequence"] == sequence and
                record["previous_record_sha256"] == previous,
                "CHAIN_LINK_MISMATCH: record was replaced, reordered or unlinked")
        zip_path = validate_path(root, record["archive_path"], ".zip")
        receipt_path = validate_path(root, record["receipt_path"], ".json")
        require(record["archive_path"] not in used_archives and
                record["receipt_path"] not in used_receipts and
                record["archive_sha256"] not in used_archives and
                record["receipt_sha256"] not in used_receipts,
                "REPLAYED_EVIDENCE: the same archive or receipt is listed twice")
        used_archives.update((record["archive_path"], record["archive_sha256"]))
        used_receipts.update((record["receipt_path"], record["receipt_sha256"]))
        checked = replay.replay(
            zip_path, record["archive_sha256"],
            receipt_path, record["receipt_sha256"])
        require(checked["result"] == "PINNED_REPORT_REPRODUCED" and
                checked["canonical_snapshot_sha256"] == record["snapshot_sha256"],
                "CHAIN_REPORT_MISMATCH: archived report has drifted")
        receipt = replay.read_receipt(receipt_path, record["receipt_sha256"])
        require(receipt["snapshot"]["handoff_review"] == record["handoff_review"],
                "CHAIN_REVIEW_MISMATCH: record changed review outcome")
        entries.append({
            "sequence": sequence,
            "record_sha256": record_hash,
            "archive_sha256": record["archive_sha256"],
            "receipt_sha256": record["receipt_sha256"],
            "handoff_review": record["handoff_review"],
        })
        previous = record_hash
    require(previous == expected_head,
            "CHAIN_HEAD_MISMATCH: last record differs from out-of-band anchor")
    return {
        "result": "PINNED_RECEIPT_CHAIN_REPLAYED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "count": len(entries),
        "chain_head_sha256": previous,
        "entries": entries,
        "physical_independence": "NOT_ATTESTED",
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "limitations": (
            "A pinned count and head only detect changes relative to the "
            "independently stored original anchors. An attacker who replaces "
            "the chain AND its trusted anchor can fabricate a consistent "
            "history. Distinct ZIPs do not prove independent Switch launches."
        ),
    }


def append(storage: Path, archive_path: str, receipt_path: str,
           archive_sha: str, receipt_sha: str,
           expected_head: str, expected_count: int) -> dict:
    require(type(expected_count) is int and expected_count < MAX_RECORDS,
            "maximum 64 chained entries")
    previous = verify(storage, expected_head, expected_count)
    root, directory = get_chain_dir(storage)
    zip_file = validate_path(root, archive_path, ".zip")
    receipt_file = validate_path(root, receipt_path, ".json")
    require(zip_file != receipt_file, "archive and receipt cannot be the same file")
    require(all(entry["archive_sha256"] != archive_sha and
                entry["receipt_sha256"] != receipt_sha
                for entry in previous["entries"]),
            "REPLAYED_EVIDENCE: archive and receipt must be new to this chain")
    checked = replay.replay(zip_file, anchor(archive_sha, "archive_sha256"),
                            receipt_file, anchor(receipt_sha, "receipt_sha256"))
    receipt = replay.read_receipt(receipt_file, receipt_sha)
    record = {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "sequence": expected_count + 1,
        "previous_record_sha256": expected_head,
        "archive_path": archive_path,
        "receipt_path": receipt_path,
        "archive_sha256": archive_sha,
        "receipt_sha256": receipt_sha,
        "snapshot_sha256": checked["canonical_snapshot_sha256"],
        "handoff_review": receipt["snapshot"]["handoff_review"],
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }
    body = stable_bytes(record)
    require(len(body) <= MAX_RECORD_BYTES, "new chain record too large")
    dest = directory / f"{record['sequence']:06d}.json"
    require(not dest.exists() and not dest.is_symlink(),
            "new chain record already exists; refusing overwrite")
    # Atomic exclusive publication on the same filesystem, never mutating
    # earlier records or any ZIP/receipt.
    handle = tempfile.NamedTemporaryFile(
        mode="wb", prefix=".stage226-", suffix=".tmp", dir=directory,
        delete=False)
    temp = Path(handle.name)
    try:
        with handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, dest)
    finally:
        temp.unlink(missing_ok=True)
    require(sha256(dest.read_bytes()) == sha256(body),
            "newly published chain record differs from in-memory bytes")
    return {
        "result": "CHAIN_RECORD_APPENDED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "count": expected_count + 1,
        "record_path": str(dest),
        "chain_head_sha256": sha256(body),
        "previous_head_sha256": expected_head,
        "save_head_and_count_out_of_band": True,
        "physical_independence": "NOT_ATTESTED",
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("append", "verify"):
        cmd = sub.add_parser(action)
        cmd.add_argument("storage_root", type=Path)
        cmd.add_argument("--expected-head-sha256", required=True)
        cmd.add_argument("--expected-count", required=True, type=int)
        if action == "append":
            cmd.add_argument("--archive", required=True)
            cmd.add_argument("--receipt", required=True)
            cmd.add_argument("--archive-sha256", required=True)
            cmd.add_argument("--receipt-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "append":
            result = append(args.storage_root, args.archive, args.receipt,
                            args.archive_sha256, args.receipt_sha256,
                            args.expected_head_sha256, args.expected_count)
        else:
            result = verify(args.storage_root, args.expected_head_sha256,
                            args.expected_count)
    except (ChainError, replay.ReplayError, cross_host.ComparisonError,
            archive.ArchiveError, handoff.HandoffError, operator.OperatorError,
            bundle.BundleError, audio.LogFormatError,
            OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
