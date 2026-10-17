#!/usr/bin/env python3
"""Stage 237: deterministic unsigned final H05 review receipt and exact replay.

seal: run complete stage-236 operator/H05 audit AND stage-222 evidence inventory,
      capture every original file digest, contradiction, missing card, H01-H07
      status and followup in one canonical read-only review receipt.
replay: require SHA-256 of original receipt pinned *outside* the receipt, then
        rerun BOTH upstream audits and compare canonical receipt bytes.

No physical Switch, removable SD identity, heard music, operator authenticity
or independent second launch is attested. INVESTIGATE/INCONCLUSIVE are preserved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as first_run
import audit_switch_audio_handoff as handoff
import capture_switch_audio_sd_csv as capture
import verify_switch_audio_bundle as bundle
import verify_switch_audio_h05_capture_binding as h05_binding
import verify_switch_audio_h05_csv_persistence as h05
import verify_switch_audio_h05_operator_binding as operator_binding
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-h05-final-review/v1"
MAX_RECEIPT = 512 * 1024
ACCEPTED_RESULTS = {
    "READY_FOR_INDEPENDENT_MANUAL_REVIEW", "INCONCLUSIVE", "INVESTIGATE"
}


class SealError(ValueError):
    """Pinned final report was modified, is in an unsafe path, or cannot replay."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SealError(message)


def stable(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def args_for_audit(source: Path, plan: Path, captured: Path,
                   baseline: Path, baseline_sha: str, review: Path,
                   review_sha: str, observations: Path, cards: Path,
                   require_h06: bool, compare_builds: bool) -> dict:
    return dict(
        source_bundle=source,
        plan=plan,
        captured=captured,
        baseline=baseline,
        baseline_sha256=baseline_sha,
        review=review,
        review_sha256=review_sha,
        observations=observations,
        cards_dir=cards,
        require_h06=require_h06,
        compare_builds=compare_builds,
    )


def source_boundaries(path: Path, source: Path, captured: Path,
                      baseline: Path, review: Path,
                      observations: Path, cards: Path, plan: Path) -> None:
    require(path.parent.is_dir() and not path.parent.is_symlink() and
            not path.is_symlink(), "final review receipt parent missing or symlinked")
    destination = path.absolute().resolve()
    for root in (source, captured, cards):
        resolved = root.resolve()
        require(not destination.is_relative_to(resolved),
                "final review receipt must remain outside source, archive and cards")
    for item in (baseline, review, observations, plan):
        require(destination != item.absolute().resolve(),
                "final review receipt must not overwrite an original source")


def snapshot(*, source_bundle: Path, plan: Path, captured: Path,
             baseline: Path, baseline_sha256: str, review: Path,
             review_sha256: str, observations: Path, cards_dir: Path,
             require_h06: bool = False, compare_builds: bool = False) -> dict:
    params = args_for_audit(
        source_bundle, plan, captured, baseline, baseline_sha256,
        review, review_sha256, observations, cards_dir, require_h06, compare_builds)
    # Independent from any previous reported result. The stage-236 verifier
    # itself recomputes stage 235 and 222; we also capture the full 222 audit.
    verified = operator_binding.verify(**params)
    audited = handoff.audit(captured, observations, cards_dir,
                           require_h06=require_h06, compare_builds=compare_builds)
    require(verified["hardware_status"] == bundle.HARDWARE_STATUS and
            audited["hardware_status"] == bundle.HARDWARE_STATUS and
            verified["result"] in ACCEPTED_RESULTS and
            verified["handoff_result"] == audited["result"] and
            verified["acceptance_matrix"] == audited["acceptance_matrix"],
            "recomputed stage 236 and stage 222 decisions disagree")
    # Ensure all source files are included, rather than merely the two H05 cards.
    source_files = audited["source_inventory"]
    require(len(source_files) >= 4 and
            any(item["role"] == "operator_claims" for item in source_files),
            "stage 222 source inventory is incomplete")
    paths = [item["name"] for item in source_files]
    require(len(paths) == len(set(paths)), "stage 222 inventory repeats a name")
    manifest = bundle.read_manifest(captured)
    require(len([i for i in source_files if i["role"] == "raw_csv"]) ==
            len(manifest["sessions"]), "some original CSVs are not inventoried")
    require(
        len([i for i in source_files
             if i["role"] == "self_reported_session_card"]) ==
        audited["repeated_session_claims"]["cards_present"],
        "operator card inventory is incomplete")
    require(verified["operator_observations_sha256"] ==
            bundle.digest_file(observations)[1] and
            verified["captured_manifest_sha256"] ==
            bundle.digest_file(captured / bundle.MANIFEST_NAME)[1],
            "original evidence changed while gathering review inventory")
    for item in source_files:
        require(bundle.SHA256_RE.fullmatch(item["sha256"]) is not None and
                type(item["size"]) is int and item["size"] > 0,
                "invalid file SHA/size from upstream audit")
    return {
        "schema": SCHEMA,
        "result": verified["result"],
        "hardware_status": bundle.HARDWARE_STATUS,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "git_sha_self_reported": audited["build"]["git_sha_self_reported"],
        "nro_sha256": audited["build"]["nro_sha256"],
        "source_manifest_sha256": bundle.digest_file(
            source_bundle / bundle.MANIFEST_NAME)[1],
        "transfer_plan_sha256": bundle.digest_file(plan)[1],
        "h05_baseline_sha256": baseline_sha256,
        "h05_review_sha256": review_sha256,
        "captured_manifest_sha256": verified["captured_manifest_sha256"],
        "operator_observations_sha256": verified["operator_observations_sha256"],
        "audit_options": {
            "require_h06": require_h06, "compare_builds": compare_builds,
        },
        "operator_binding": verified,
        "entire_source_inventory": source_files,
        "all_session_cards": audited["session_cards"],
        "self_reported_repeatability": audited["repeated_session_claims"],
        "full_handoff_contradictions": audited["contradictions"],
        "full_handoff_retests": audited["retests"],
        "full_handoff_followups": audited["handoff_followups"],
        "full_acceptance_matrix": audited["acceptance_matrix"],
        "physical_switch_execution": "NOT_ATTESTED",
        "physical_session_independence": "NOT_ATTESTED",
        "audible_music": "NOT_ATTESTED",
        "limitations": (
            "Exact source bytes and operator claims are repeatably audited. "
            "Receipt is unsigned and not hardware certification; timestamps, "
            "SD provenance, distinct physical launches and audible music "
            "require independent manual verification."
        ),
    }


def seal(output: Path, **params) -> dict:
    source_boundaries(output, params["source_bundle"], params["captured"],
                      params["baseline"], params["review"],
                      params["observations"], params["cards_dir"],
                      params["plan"])
    require(not output.exists(), "final review already exists; refusing overwrite")
    report = snapshot(**params)
    raw = stable(report)
    require(len(raw) <= MAX_RECEIPT,
            "final review exceeds 512 KiB receipt limit")
    with output.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return {
        "result": "H05_FINAL_REVIEW_RECEIPT_SEALED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "review_state": report["result"],
        "receipt_sha256": digest(raw),
        "total_source_files": len(report["entire_source_inventory"]),
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "physical_switch_execution": "NOT_ATTESTED",
        "next_action": "Save receipt_sha256 independently, then use replay.",
    }


def replay(receipt: Path, independent_sha256: str, **params) -> dict:
    source_boundaries(receipt, params["source_bundle"], params["captured"],
                      params["baseline"], params["review"],
                      params["observations"], params["cards_dir"],
                      params["plan"])
    require(isinstance(independent_sha256, str) and
            bundle.SHA256_RE.fullmatch(independent_sha256) is not None,
            "independently pinned review SHA-256 must be 64 lowercase hex characters")
    require(receipt.is_file() and not receipt.is_symlink() and
            0 < receipt.stat().st_size <= MAX_RECEIPT,
            "final review receipt missing, symlinked or oversized")
    raw = receipt.read_bytes()
    require(len(raw) <= MAX_RECEIPT and digest(raw) == independent_sha256,
            "FINAL_REVIEW_SHA256_MISMATCH")
    try:
        value = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SealError(f"invalid final review JSON: {exc}") from exc
    require(isinstance(value, dict) and value.get("schema") == SCHEMA and
            value.get("hardware_status") == bundle.HARDWARE_STATUS and
            value.get("manual_signoff") == "REQUIRED_NOT_AUTOMATED",
            "final review falsely claims hardware PASS or has wrong schema")
    require(raw == stable(value), "noncanonical final review JSON")
    actual = snapshot(**params)
    require(stable(actual) == raw, "FINAL_REVIEW_REPLAY_MISMATCH")
    require(digest(receipt.read_bytes()) == independent_sha256,
            "final review changed while being replayed")
    return {
        "result": "PINNED_H05_FINAL_REVIEW_REPLAYED",
        "hardware_status": bundle.HARDWARE_STATUS,
        "review_state": actual["result"],
        "receipt_sha256": independent_sha256,
        "total_source_files": len(actual["entire_source_inventory"]),
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "physical_switch_execution": "NOT_ATTESTED",
    }


def common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--source-bundle", required=True, type=Path)
    p.add_argument("--transfer-plan", required=True, type=Path)
    p.add_argument("--captured", required=True, type=Path)
    p.add_argument("--h05-baseline", required=True, type=Path)
    p.add_argument("--baseline-sha256", required=True)
    p.add_argument("--h05-review", required=True, type=Path)
    p.add_argument("--review-sha256", required=True)
    p.add_argument("--observations", required=True, type=Path)
    p.add_argument("--cards-dir", required=True, type=Path)
    p.add_argument("--require-h06", action="store_true")
    p.add_argument("--compare-builds", action="store_true")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    issue = sub.add_parser("seal")
    common_args(issue)
    issue.add_argument("--output", required=True, type=Path)
    check = sub.add_parser("replay")
    common_args(check)
    check.add_argument("--receipt", required=True, type=Path)
    check.add_argument("--expected-receipt-sha256", required=True)
    args = parser.parse_args(argv)
    params = dict(
        source_bundle=args.source_bundle, plan=args.transfer_plan,
        captured=args.captured, baseline=args.h05_baseline,
        baseline_sha256=args.baseline_sha256, review=args.h05_review,
        review_sha256=args.review_sha256, observations=args.observations,
        cards_dir=args.cards_dir, require_h06=args.require_h06,
        compare_builds=args.compare_builds)
    try:
        if args.command == "seal":
            result = seal(args.output, **params)
        else:
            result = replay(args.receipt, args.expected_receipt_sha256, **params)
    except (SealError, operator_binding.OperatorBindingError,
            h05_binding.BindingError, h05.PersistenceError,
            first_run.OperatorError, handoff.HandoffError,
            capture.CaptureError, transfer.TransferError,
            bundle.BundleError, audio.LogFormatError,
            OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({
            "result": "INVALID_EVIDENCE",
            "hardware_status": bundle.HARDWARE_STATUS,
            "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
