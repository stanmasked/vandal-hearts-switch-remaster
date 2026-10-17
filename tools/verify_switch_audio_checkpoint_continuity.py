#!/usr/bin/env python3
"""Stage 228: prove that a later chain preserves an independently pinned checkpoint.

Unlike cross-copy comparison (stage 227), the earlier checkpoint may no longer
have a separate archived root: the same storage has grown since its creation.
Read the immutable prior checkpoint with its out-of-band SHA-256, replay the
ENTIRE current chain and checkpoint, then prove the previous ordered entries
and old head are an exact prefix. No ZIP, CSV or receipt is changed.

Only source bytes and consistency are verified. No digital signature,
physical session independence, audible audio or hardware PASS is established.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_switch_audio_log as audio
import archive_switch_audio_handoff as archive
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import chain_switch_audio_receipts as chain
import checkpoint_switch_audio_receipt_chain as checkpoint
import compare_switch_audio_archive_reports as cross_host
import replay_switch_audio_evidence_report as replay
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-checkpoint-continuity/v1"


class ContinuityError(ValueError):
    """Strictly rejected history mutation, rollback or mismatched anchor."""


def require(ok: bool, detail: str) -> None:
    if not ok:
        raise ContinuityError(detail)


def assess_continuity(prior: dict, current: dict, *,
                      require_growth: bool = False) -> dict:
    """Compare two structurally sound checkpoints; caller replays current root."""
    checkpoint.validated_checkpoint(prior)
    checkpoint.validated_checkpoint(current)
    require(type(require_growth) is bool, "require_growth must be boolean")
    before = prior["count"]
    now = current["count"]
    require(now >= before,
            "HISTORY_ROLLBACK: current history has fewer entries than prior anchor")
    require(current["entries"][:before] == prior["entries"],
            "HISTORY_PREFIX_DIVERGED: earlier recorded evidence was changed or reordered")
    require(current["chain_head_sha256"] == (
            current["entries"][-1]["record_sha256"] if now else chain.GENESIS),
            "HISTORY_CURRENT_HEAD_MISMATCH")
    require(before == 0 or
            current["entries"][before - 1]["record_sha256"] ==
            prior["chain_head_sha256"],
            "HISTORY_OLD_HEAD_NOT_RETAINED")
    if before == 0:
        require(prior["chain_head_sha256"] == chain.GENESIS,
                "HISTORY_INVALID_GENESIS")
    added = current["entries"][before:]
    if require_growth:
        require(bool(added),
                "HISTORY_NO_GROWTH: at least one new verified record is required")
    require(all(item["sequence"] == i + before + 1
                for i, item in enumerate(added)), "HISTORY_NEW_RECORD_ORDER_INVALID")
    return {
        "schema": SCHEMA,
        "result": ("CONTINUITY_PRESERVED_WITH_NEW_RECORDS" if added
                   else "CONTINUITY_PRESERVED_NO_GROWTH"),
        "hardware_status": bundle.HARDWARE_STATUS,
        "prior_count": before,
        "current_count": now,
        "new_records": len(added),
        "prior_chain_head_sha256": prior["chain_head_sha256"],
        "current_chain_head_sha256": current["chain_head_sha256"],
        "prior_entries_sha256": prior["entries_sha256"],
        "current_entries_sha256": current["entries_sha256"],
        "new_record_inventory": [
            {"sequence": row["sequence"], "record_sha256": row["record_sha256"],
             "archive_sha256": row["archive_sha256"],
             "receipt_sha256": row["receipt_sha256"],
             "handoff_review": row["handoff_review"]}
            for row in added
        ],
        "old_records_changed": False,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "physical_independence": "NOT_ATTESTED",
        "limitations": (
            "The prior checkpoint is anchored by an independently saved SHA-256 "
            "but need not have a separate historic storage folder. The current "
            "chain, ZIPs, receipts and CSV/NRO evidence were all re-audited. "
            "Matching data do not prove distinct physical Switch launches, "
            "audible playback, SD durability, original authorship or hardware PASS."
        ),
    }


def verify_continuity(
        prior_checkpoint: Path, prior_checkpoint_sha256: str,
        prior_head_sha256: str, prior_count: int,
        current_root: Path, current_checkpoint: Path,
        current_checkpoint_sha256: str, current_head_sha256: str,
        current_count: int, *, require_growth: bool = False) -> dict:
    chain.anchor(prior_head_sha256, "independently pinned prior chain head")
    require(type(prior_count) is int and 0 <= prior_count <= chain.MAX_RECORDS,
            "invalid independently pinned prior count")
    pinned_prior = checkpoint.read_checkpoint(
        prior_checkpoint, prior_checkpoint_sha256)
    require(pinned_prior["count"] == prior_count and
            pinned_prior["chain_head_sha256"] == prior_head_sha256,
            "HISTORY_PRIOR_ANCHOR_MISMATCH: old checkpoint disagrees with saved count/head")
    pinned_current = checkpoint.reread_and_replay(
        current_root, current_checkpoint, current_checkpoint_sha256,
        current_head_sha256, current_count)
    require(pinned_current["count"] == current_count and
            pinned_current["chain_head_sha256"] == current_head_sha256,
            "HISTORY_CURRENT_ANCHOR_MISMATCH")
    result = assess_continuity(
        pinned_prior, pinned_current, require_growth=require_growth)
    result["prior_checkpoint_sha256"] = prior_checkpoint_sha256
    result["current_checkpoint_sha256"] = current_checkpoint_sha256
    result["current_root_fully_replayed"] = True
    result["prior_checkpoint_bytes_pinned"] = True
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-checkpoint", required=True, type=Path)
    parser.add_argument("--prior-checkpoint-sha256", required=True)
    parser.add_argument("--prior-head-sha256", required=True)
    parser.add_argument("--prior-count", required=True, type=int)
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--current-checkpoint", required=True, type=Path)
    parser.add_argument("--current-checkpoint-sha256", required=True)
    parser.add_argument("--current-head-sha256", required=True)
    parser.add_argument("--current-count", required=True, type=int)
    parser.add_argument("--require-growth", action="store_true",
                        help="reject an unchanged history as incomplete follow-up")
    args = parser.parse_args(argv)
    try:
        result = verify_continuity(
            args.prior_checkpoint, args.prior_checkpoint_sha256,
            args.prior_head_sha256, args.prior_count,
            args.current_root, args.current_checkpoint,
            args.current_checkpoint_sha256, args.current_head_sha256,
            args.current_count, require_growth=args.require_growth)
    except (ContinuityError, checkpoint.CheckpointError,
            chain.ChainError, replay.ReplayError, cross_host.ComparisonError,
            archive.ArchiveError, handoff.HandoffError,
            operator.OperatorError, bundle.BundleError,
            audio.LogFormatError, OSError, KeyError,
            TypeError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
