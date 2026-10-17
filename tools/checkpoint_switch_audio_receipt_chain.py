#!/usr/bin/env python3
"""Stage 227: independently pinned history checkpoints and cross-copy comparison.

checkpoint: replays a stage-226 chain and writes a stable canonical JSON
            checkpoint outside the evidence storage, without overwriting.
compare:    validates each checkpoint against its separately pinned SHA-256,
            replays BOTH histories against separately pinned head AND count,
            checks that saved checkpoint matches that full replay, and
            identifies identical, appended or genuinely divergent histories.

This is a local integrity/reproducibility test, not a digital signature or
Nintendo Switch hardware acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import analyze_switch_audio_log as audio
import archive_switch_audio_handoff as archive
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import chain_switch_audio_receipts as chain
import compare_switch_audio_archive_reports as cross_host
import replay_switch_audio_evidence_report as replay
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-history-checkpoint/v1"
COMPARE_SCHEMA = "vh-switch-audio-history-cross-copy/v1"
MAX_CHECKPOINT = 64 * 1024
CHECKPOINT_KEYS = {
    "schema", "hardware_status", "chain_head_sha256", "count",
    "entries_sha256", "entries", "physical_independence", "manual_signoff",
}
ENTRY_KEYS = {"sequence", "record_sha256", "archive_sha256",
              "receipt_sha256", "handoff_review"}
REVIEW_VALUES = {"INCONCLUSIVE", "INVESTIGATE",
                 "READY_FOR_INDEPENDENT_MANUAL_REVIEW"}


class CheckpointError(ValueError):
    """Pinned checkpoint, chain or cross-copy audit discrepancy."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise CheckpointError(reason)


def to_bytes(data: dict) -> bytes:
    return chain.stable_bytes(data)


def entries_sha256(entries: list) -> str:
    return chain.sha256(replay.canonical_bytes({"entries": entries}))


def canonical_checkpoint(verified: dict) -> dict:
    require(verified["result"] == "PINNED_RECEIPT_CHAIN_REPLAYED" and
            verified["hardware_status"] == bundle.HARDWARE_STATUS,
            "chain must be independently verified")
    entries = verified["entries"]
    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "chain_head_sha256": verified["chain_head_sha256"],
        "count": verified["count"],
        "entries_sha256": entries_sha256(entries),
        "entries": entries,
        "physical_independence": "NOT_ATTESTED",
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def validated_checkpoint(data: object) -> dict:
    require(isinstance(data, dict) and set(data) == CHECKPOINT_KEYS and
            data.get("schema") == SCHEMA and
            data.get("hardware_status") == bundle.HARDWARE_STATUS and
            data.get("physical_independence") == "NOT_ATTESTED" and
            data.get("manual_signoff") == "REQUIRED_NOT_AUTOMATED",
            "unsupported checkpoint schema or forged hardware status")
    n = data["count"]
    require(type(n) is int and 0 <= n <= chain.MAX_RECORDS,
            "invalid checkpoint record count")
    require(isinstance(data["entries"], list) and len(data["entries"]) == n,
            "checkpoint entries do not match count")
    chain.anchor(data["chain_head_sha256"], "checkpoint head SHA-256")
    chain.anchor(data["entries_sha256"], "checkpoint entries SHA-256")
    for i, entry in enumerate(data["entries"], 1):
        require(isinstance(entry, dict) and set(entry) == ENTRY_KEYS and
                type(entry["sequence"]) is int and entry["sequence"] == i and
                isinstance(entry["handoff_review"], str) and
                entry["handoff_review"] in REVIEW_VALUES,
                "invalid or out-of-order checkpoint entry")
        for key in ("record_sha256", "archive_sha256", "receipt_sha256"):
            chain.anchor(entry[key], key)
    require(data["chain_head_sha256"] ==
            (data["entries"][-1]["record_sha256"] if n else chain.GENESIS),
            "checkpoint head does not match final recorded link")
    require(data["entries_sha256"] == entries_sha256(data["entries"]),
            "checkpoint entry digest mismatch")
    return data


def read_checkpoint(path: Path, expected_sha256: str) -> dict:
    chain.anchor(expected_sha256, "independent checkpoint SHA-256")
    require(path.is_file() and not path.is_symlink(),
            "checkpoint missing or symbolic link")
    require(path.stat().st_size <= MAX_CHECKPOINT,
            "checkpoint exceeds size bound")
    raw = path.read_bytes()
    require(chain.sha256(raw) == expected_sha256,
            "CHECKPOINT_SHA256_MISMATCH: checkpoint differs from independent pin")
    try:
        value = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"invalid checkpoint JSON: {exc}") from exc
    obj = validated_checkpoint(value)
    require(raw == to_bytes(obj), "NONCANONICAL_CHECKPOINT: bytes do not match canonical JSON")
    return obj


def full_replay(storage: Path, head: str, count: int) -> dict:
    return canonical_checkpoint(chain.verify(storage, head, count))


def create_checkpoint(storage: Path, head: str, count: int,
                      output: Path) -> dict:
    require(output.parent.is_dir(), "checkpoint output parent missing")
    require(not output.exists() and not output.is_symlink(),
            "checkpoint already exists; refusing overwrite")
    root, _ = chain.get_chain_dir(storage)
    require(not output.absolute().resolve().is_relative_to(root),
            "checkpoint output must be outside the evidence storage root")
    checkpoint = full_replay(storage, head, count)
    raw = to_bytes(checkpoint)
    require(len(raw) <= MAX_CHECKPOINT, "checkpoint exceeds 64 KiB")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "result": "INDEPENDENT_HISTORY_CHECKPOINT_CREATED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "chain_head_sha256": head,
        "count": count,
        "checkpoint_sha256": chain.sha256(raw),
        "save_checkpoint_hash_out_of_band": True,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
    }


def reread_and_replay(storage: Path, checkpoint_file: Path,
                      checkpoint_hash: str, head: str, count: int) -> dict:
    pinned = read_checkpoint(checkpoint_file, checkpoint_hash)
    chain.anchor(head, "independently pinned chain head")
    require(type(count) is int and 0 <= count <= chain.MAX_RECORDS,
            "independent chain count must be 0..64")
    require(pinned["chain_head_sha256"] == head and pinned["count"] == count,
            "CHECKPOINT_ANCHOR_MISMATCH: count/head differ from independent pin")
    fresh = full_replay(storage, head, count)
    require(pinned == fresh,
            "CHECKPOINT_REPORT_DRIFT: checkpoint differs from fresh complete replay")
    return fresh


def compare_histories(source: dict, received: dict) -> dict:
    """Only call after independently re-verifying both pinned checkpoints."""
    validated_checkpoint(source)
    validated_checkpoint(received)
    earlier, later = source["entries"], received["entries"]
    changes = []
    for i in range(max(len(earlier), len(later))):
        left = earlier[i] if i < len(earlier) else None
        right = later[i] if i < len(later) else None
        if left == right:
            continue
        changes.append({
            "sequence": i + 1,
            "code": ("MISSING_IN_RECEIVED_COPY" if right is None else
                     "ADDED_IN_RECEIVED_COPY" if left is None else
                     "DIVERGENT_CHAIN_ENTRY"),
            "source": left, "received": right,
        })
    if not changes:
        outcome = "EXACT_HISTORY_MATCH"
    elif len(earlier) < len(later) and earlier == later[:len(earlier)]:
        outcome = "RECEIVED_HISTORY_EXTENDED"
    elif len(later) < len(earlier) and later == earlier[:len(later)]:
        outcome = "RECEIVED_HISTORY_SHORTER"
    else:
        outcome = "DIVERGENT_VALID_HISTORIES"
    return {
        "schema": COMPARE_SCHEMA,
        "result": outcome,
        "hardware_status": bundle.HARDWARE_STATUS,
        "source_head_sha256": source["chain_head_sha256"],
        "received_head_sha256": received["chain_head_sha256"],
        "source_count": source["count"],
        "received_count": received["count"],
        "differences": changes,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "physical_independence": "NOT_ATTESTED",
        "limitations": (
            "Both chains were rechecked against separately supplied heads, counts "
            "and checkpoint digests. Shortened or divergent but internally valid "
            "history is not an identical copy. SHA-256 does not authenticate a "
            "person, physical console, audible audio or independent launches."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    capture = actions.add_parser("checkpoint", help="write a canonical pinned checkpoint")
    capture.add_argument("storage_root", type=Path)
    capture.add_argument("--expected-head-sha256", required=True)
    capture.add_argument("--expected-count", required=True, type=int)
    capture.add_argument("--output", required=True, type=Path)
    comparison = actions.add_parser("compare", help="compare two pinned reverified histories")
    for role in ("source", "received"):
        comparison.add_argument("--" + role + "-root", required=True, type=Path)
        comparison.add_argument("--" + role + "-checkpoint", required=True, type=Path)
        comparison.add_argument("--" + role + "-checkpoint-sha256", required=True)
        comparison.add_argument("--" + role + "-head-sha256", required=True)
        comparison.add_argument("--" + role + "-count", required=True, type=int)
    args = parser.parse_args(argv)
    try:
        if args.action == "checkpoint":
            report = create_checkpoint(args.storage_root,
                                       args.expected_head_sha256,
                                       args.expected_count, args.output)
        else:
            source = reread_and_replay(
                args.source_root, args.source_checkpoint,
                args.source_checkpoint_sha256, args.source_head_sha256,
                args.source_count)
            received = reread_and_replay(
                args.received_root, args.received_checkpoint,
                args.received_checkpoint_sha256, args.received_head_sha256,
                args.received_count)
            report = compare_histories(source, received)
    except (CheckpointError, chain.ChainError, replay.ReplayError,
            cross_host.ComparisonError, archive.ArchiveError,
            handoff.HandoffError, operator.OperatorError, bundle.BundleError,
            audio.LogFormatError, OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
