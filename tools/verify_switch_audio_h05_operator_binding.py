#!/usr/bin/env python3
"""Stage 236: join pinned H05 raw CSV evidence to operator session cards.

Recompute stage-235 H05 baseline/review/captured-bundle validation and stage-222
operator handoff; verify that the old and new H05 CSV map to distinct ordered
operator session IDs, exact original CSV hashes and NRO, and nonoverlapping
self-reported launches. No file is changed, and a consistent report is NEVER
a hardware PASS or independent physical launch attestation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as first_run
import audit_switch_audio_handoff as handoff
import capture_switch_audio_sd_csv as capture
import verify_switch_audio_bundle as bundle
import verify_switch_audio_h05_capture_binding as h05_binding
import verify_switch_audio_h05_csv_persistence as h05
import verify_switch_audio_sd_transfer as transfer

SCHEMA = "vh-switch-audio-h05-operator-binding/v1"


class OperatorBindingError(ValueError):
    """An H05 CSV, operator-card identity or provenance assertion differs."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise OperatorBindingError(reason)


def verify(source_bundle: Path, plan: Path, captured: Path,
           baseline: Path, baseline_sha256: str, review: Path,
           review_sha256: str, observations: Path, cards_dir: Path,
           *, require_h06: bool = False, compare_builds: bool = False) -> dict:
    require(observations.is_file() and not observations.is_symlink() and
            not observations.resolve().is_relative_to(captured.resolve()),
            "operator observations must be outside captured bundle")
    require(cards_dir.is_dir() and not cards_dir.is_symlink() and
            not cards_dir.resolve().is_relative_to(captured.resolve()),
            "operator cards must be outside captured bundle")

    matched = h05_binding.examine(
        source_bundle, plan, captured, baseline,
        baseline_sha256, review, review_sha256)
    require(matched["result"] ==
            "H05_CAPTURED_EVIDENCE_CONSISTENT_FOR_MANUAL_REVIEW" and
            matched["hardware_status"] == bundle.HARDWARE_STATUS,
            "stage 235 has not confirmed the pinned H05 CSV archive")
    audited = handoff.audit(captured, observations, cards_dir,
                           require_h06=require_h06,
                           compare_builds=compare_builds)
    require(audited["hardware_status"] == bundle.HARDWARE_STATUS and
            audited["manual_signoff"] == "REQUIRED_NOT_AUTOMATED",
            "stage 222 attempted automated hardware certification")
    manifest = bundle.read_manifest(captured)
    claims = first_run.read_observations(observations)
    old, new = matched["old_csv"], matched["new_csv"]
    require(claims["build_git_sha"] == matched["git_sha_self_reported"] and
            claims["nro_sha256"] == matched["nro_sha256"],
            "H05_OPERATOR_BUILD_OR_NRO_MISMATCH")
    by_csv = {item["csv"]: (i, item) for i, item in enumerate(claims["sessions"])}
    require(len(by_csv) == len(claims["sessions"]),
            "duplicate claimed CSV session")
    require(old["captured_path"] in by_csv and
            new["captured_path"] in by_csv,
            "H05_OPERATOR_OLD_OR_NEW_CSV_NOT_MAPPED")
    old_index, old_session = by_csv[old["captured_path"]]
    new_index, new_session = by_csv[new["captured_path"]]
    require(old_index < new_index and
            old_session["id"] != new_session["id"],
            "H05_OPERATOR_OLD_NEW_SESSION_ORDER_WRONG")
    missing = []
    problems = []
    cards = {}
    csv_by_path = {v["path"]: v for v in manifest["sessions"]}
    for label, source in (("old", old_session), ("new", new_session)):
        name = source["id"] + ".json"
        card_path = cards_dir / name
        if not card_path.is_file():
            missing.append({"session": source["id"],
                            "code": "H05_OPERATOR_CARD_MISSING", "role": label})
            continue
        card = handoff.read_card(card_path)
        target = old if label == "old" else new
        expected_csv = target["captured_path"]
        if (card["session_id"] != source["id"] or
                card["csv"] != expected_csv or
                card["csv_sha256"] != target["sha256"] or
                card["nro_sha256"] != matched["nro_sha256"] or
                card["git_sha"] != matched["git_sha_self_reported"]):
            problems.append({"session": source["id"],
                             "code": "H05_OPERATOR_CARD_CSV_BUILD_IDENTITY_MISMATCH",
                             "role": label})
        else:
            require(card["csv_sha256"] ==
                    csv_by_path[expected_csv]["sha256"],
                    "H05_OPERATOR_CARD_DISAGREES_WITH_CAPTURED_MANIFEST")
        cards[label] = card

    if "old" in cards and "new" in cards:
        one, two = cards["old"], cards["new"]
        if one["launch_id"] == two["launch_id"]:
            problems.append({"session": new_session["id"],
                             "code": "H05_REUSED_SELF_REPORTED_LAUNCH_ID"})
        if handoff.parse_time(one["end_utc"]) >= handoff.parse_time(two["start_utc"]):
            problems.append({"session": new_session["id"],
                             "code": "H05_OVERLAPPING_OPERATOR_SESSION_TIMES"})
        if one["console_label"] != two["console_label"]:
            problems.append({"session": new_session["id"],
                             "code": "H05_CONSOLE_LABEL_CHANGED"})
    if claims.get("prior_csv_path") != old["captured_path"]:
        problems.append({"session": old_session["id"],
                         "code": "H05_OPERATOR_PRIOR_CSV_PATH_MISMATCH"})
    if (claims["prior_csv_sha256_before"] != old["sha256"] or
            claims["prior_csv_sha256_after"] != old["sha256"]):
        problems.append({"session": old_session["id"],
                         "code": "H05_OPERATOR_PRIOR_CSV_HASHES_MISMATCH"})
    if audited["result"] == "INVESTIGATE" or problems:
        classification = "INVESTIGATE"
    elif audited["result"] != "READY_FOR_INDEPENDENT_MANUAL_REVIEW" or missing:
        classification = "INCONCLUSIVE"
    else:
        classification = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"
    result = {
        "schema": SCHEMA,
        "result": classification,
        "hardware_status": bundle.HARDWARE_STATUS,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "h05_baseline_sha256": baseline_sha256,
        "h05_review_sha256": review_sha256,
        "captured_manifest_sha256": matched["captured_manifest_sha256"],
        "operator_observations_sha256": bundle.digest_file(observations)[1],
        "old_csv": {"session_id": old_session["id"],
                    "path": old["captured_path"], "sha256": old["sha256"]},
        "new_csv": {"session_id": new_session["id"],
                    "path": new["captured_path"], "sha256": new["sha256"]},
        "operator_card_sha256": {
            role: bundle.digest_file(cards_dir / (item["id"] + ".json"))[1]
            for role, item in (("old", old_session), ("new", new_session))
            if (cards_dir / (item["id"] + ".json")).is_file()
        },
        "operator_session_claims_ordered": True,
        "handoff_result": audited["result"],
        "missing_cards": missing,
        "contradictions": problems + audited["contradictions"],
        "acceptance_matrix": audited["acceptance_matrix"],
        "physical_session_independence": "NOT_ATTESTED",
        "actual_audio_playback": "NOT_ATTESTED",
        "limitations": (
            "Operator cards and timestamps are unsigned claims. Exact H05 CSV "
            "hashes, reported order and unique launch labels only permit "
            "independent human review, not console execution, independent "
            "launch attestation, audible sound or hardware PASS."
        ),
    }
    # Reject edits between the prior audit and finished report.
    require(h05.sha256(baseline.read_bytes()) == baseline_sha256 and
            h05.sha256(review.read_bytes()) == review_sha256 and
            bundle.digest_file(captured / bundle.MANIFEST_NAME)[1] ==
            matched["captured_manifest_sha256"],
            "H05_EVIDENCE_CHANGED_DURING_OPERATOR_AUDIT")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-bundle", type=Path, required=True)
    parser.add_argument("--transfer-plan", type=Path, required=True)
    parser.add_argument("--captured", type=Path, required=True)
    parser.add_argument("--h05-baseline", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--h05-review", type=Path, required=True)
    parser.add_argument("--review-sha256", required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--cards-dir", type=Path, required=True)
    parser.add_argument("--require-h06", action="store_true")
    parser.add_argument("--compare-builds", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(args.source_bundle, args.transfer_plan, args.captured,
                        args.h05_baseline, args.baseline_sha256, args.h05_review,
                        args.review_sha256, args.observations, args.cards_dir,
                        require_h06=args.require_h06,
                        compare_builds=args.compare_builds)
    except (OperatorBindingError, h05_binding.BindingError,
            h05.PersistenceError, handoff.HandoffError,
            first_run.OperatorError, capture.CaptureError,
            transfer.TransferError, bundle.BundleError,
            audio.LogFormatError, OSError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
