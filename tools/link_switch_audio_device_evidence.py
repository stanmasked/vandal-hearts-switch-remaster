#!/usr/bin/env python3
"""Stage 232: link pre-device SD reinsert checks to post-device CSV evidence.

Offline, read-only. Two independently pinned host-side stage 231 JSON files
bind a claimed installed NRO to a later bundle, operator observations, and
time-stamped session cards. The post-run manifest MAY have new CSV sessions
and therefore does NOT need to match the pre-run manifest SHA.

The timestamps and "Switch was tested" claim are operator assertions:
this tool cannot attest physical execution, audibility, independent sessions,
the SD hardware, or authenticity of unsigned JSON. Never yields hardware PASS.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as operator
import audit_switch_audio_handoff as handoff
import verify_switch_audio_bundle as bundle
import verify_switch_audio_sd_reinsert as reinsert

SCHEMA = "vh-switch-audio-device-evidence-link/v1"
RECHECK_SCHEMA = "vh-switch-audio-sd-reinsert-review/v1"
MAX_RECHECK = 16 * 1024
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
RECHECK_FIELDS = {
    "schema", "result", "hardware_status", "baseline_sha256",
    "build_git_sha_confirmed_at_recheck", "run_id", "artifact_id",
    "run_attempt", "installed_nro_sha256", "installed_nro_size",
    "checked_at_utc", "operator_reinsert_claim", "physical_sd_medium",
    "physical_nro_execution", "audible_music", "sd_power_loss_durability",
    "limitations",
}


class LinkError(ValueError):
    """Host evidence differs from pinned build, dates or expected structure."""


def require(test: bool, detail: str) -> None:
    if not test:
        raise LinkError(detail)


def utc(value: object) -> datetime:
    require(isinstance(value, str) and 0 < len(value) <= 40,
            "missing or oversized timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LinkError("invalid ISO date in device evidence") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() is not None,
            "device evidence timestamp lacks timezone")
    return parsed.astimezone(timezone.utc)


def sha256_file(path: Path, max_size: int) -> str:
    require(path.is_file() and not path.is_symlink(),
            "pinned evidence JSON is missing or symbolic link")
    require(0 < path.stat().st_size <= max_size,
            "pinned evidence JSON exceeds size limit")
    return bundle.digest_file(path)[1]


def read_recheck(path: Path, expected_sha256: str) -> dict:
    require(isinstance(expected_sha256, str) and
            SHA256.fullmatch(expected_sha256) is not None,
            "independent recheck SHA-256 must be exactly 64 lowercase hex digits")
    actual = sha256_file(path, MAX_RECHECK)
    require(actual == expected_sha256,
            "RECHECK_SHA256_MISMATCH: the reinsert review was replaced or edited")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"),
                         object_pairs_hook=bundle.unique_pairs,
                         parse_constant=lambda word: (_ for _ in ()).throw(
                             LinkError("non-finite JSON constant forbidden")))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise LinkError(f"invalid reinsert review JSON: {exc}") from exc
    require(isinstance(doc, dict) and set(doc) == RECHECK_FIELDS,
            "wrong stage 231 recheck report schema")
    require(doc["schema"] == RECHECK_SCHEMA and
            doc["result"] == "POST_REINSERT_LOCAL_NRO_BYTES_MATCH" and
            doc["hardware_status"] == bundle.HARDWARE_STATUS and
            doc["operator_reinsert_claim"] ==
            "SELF_REPORTED_NOT_INDEPENDENTLY_ATTESTED" and
            doc["physical_sd_medium"] == "NOT_ATTESTED" and
            doc["physical_nro_execution"] == bundle.HARDWARE_STATUS and
            doc["audible_music"] == "NOT_TESTED" and
            doc["sd_power_loss_durability"] == "NOT_TESTED",
            "stage 231 JSON falsely claims hardware acceptance or completion")
    for field in ("run_id", "artifact_id", "run_attempt", "installed_nro_size"):
        require(type(doc[field]) is int and doc[field] > 0,
                f"invalid reinsert {field}")
    for field in ("baseline_sha256", "installed_nro_sha256"):
        require(isinstance(doc[field], str) and SHA256.fullmatch(doc[field]) is not None,
                f"invalid reinsert {field}")
    require(isinstance(doc["build_git_sha_confirmed_at_recheck"], str) and
            re.fullmatch(r"[0-9a-f]{40}", doc["build_git_sha_confirmed_at_recheck"])
            is not None, "invalid reinsert Git SHA")
    require(isinstance(doc["limitations"], str) and
            0 < len(doc["limitations"]) <= 1024,
            "stage 231 limitations must not be missing")
    utc(doc["checked_at_utc"])
    return doc


def link(root: Path, observations: Path, cards: Path, baseline: Path,
         baseline_sha256: str, recheck_report: Path,
         recheck_sha256: str, *,
         require_h06: bool = False, compare_builds: bool = False) -> dict:
    require(baseline.resolve() != recheck_report.resolve(),
            "baseline and reinsert review must be separate source files")
    require(not baseline.resolve().is_relative_to(root.resolve()) and
            not recheck_report.resolve().is_relative_to(root.resolve()),
            "host-side readback records must be outside post-run evidence bundle")
    first = reinsert.read_baseline(baseline, baseline_sha256)
    after = read_recheck(recheck_report, recheck_sha256)
    require(after["baseline_sha256"] == baseline_sha256,
            "RECHECK_BASELINE_BINDING_MISMATCH")
    for old, new in (
        ("build_git_sha", "build_git_sha_confirmed_at_recheck"),
        ("run_id", "run_id"),
        ("artifact_id", "artifact_id"),
        ("run_attempt", "run_attempt"),
        ("installed_nro_sha256", "installed_nro_sha256"),
        ("installed_nro_size", "installed_nro_size"),
    ):
        require(first[old] == after[new],
                f"PRE_POST_BUILD_IDENTITY_MISMATCH: {old}")
    before_time = utc(first["checked_at_utc"])
    after_time = utc(after["checked_at_utc"])
    require(after_time >= before_time,
            "REINSERT_REVIEW_PREDATES_BASELINE")

    manifest = bundle.read_manifest(root)
    require(manifest["git_sha"] == first["build_git_sha"] and
            manifest["nro"]["sha256"] == first["installed_nro_sha256"] and
            manifest["nro"]["size"] == first["installed_nro_size"],
            "POST_RUN_BUNDLE_NRO_OR_BUILD_MISMATCH")
    expected_run = (
        "https://github.com/stanmasked/vandal-hearts-switch-remaster/"
        f"actions/runs/{first['run_id']}"
    )
    require(manifest["ci_run_url"] == expected_run,
            "POST_RUN_BUNDLE_GITHUB_RUN_URL_MISMATCH")
    analysis = handoff.audit(root, observations, cards, require_h06=require_h06,
                             compare_builds=compare_builds)

    obs = operator.read_observations(observations)
    card_rows = []
    chronology = []
    for item in obs["sessions"]:
        card_file = cards / (item["id"] + ".json")
        if not card_file.is_file():
            card_rows.append({"session": item["id"], "state": "MISSING_MANUAL_CARD"})
            continue
        card = handoff.read_card(card_file)
        start = utc(card["start_utc"])
        end = utc(card["end_utc"])
        problems = []
        if start < after_time:
            problems.append("SESSION_CLAIM_BEFORE_VERIFIED_SD_RECHECK")
        if end < start:
            problems.append("INVALID_SESSION_INTERVAL")
        if problems:
            chronology.extend({"session": item["id"], "code": problem}
                              for problem in problems)
        card_rows.append({
            "session": item["id"],
            "csv": item["csv"],
            "csv_sha256": card["csv_sha256"],
            "card_sha256": sha256_file(card_file, handoff.MAX_CARD),
            "reported_start_utc": start.isoformat(),
            "reported_end_utc": end.isoformat(),
            "state": "CLAIM_AFTER_SD_READBACK" if not problems else
                     "INCONSISTENT_CLAIM_CHRONOLOGY",
        })
    if chronology or analysis["result"] == "INVESTIGATE":
        result = "INVESTIGATE"
    elif analysis["result"] == "INCONCLUSIVE" or any(
            row["state"] == "MISSING_MANUAL_CARD" for row in card_rows):
        result = "INCONCLUSIVE"
    else:
        result = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"

    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "result": result,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "build": {
            "git_sha_self_reported": first["build_git_sha"],
            "run_id_self_reported": first["run_id"],
            "artifact_id_self_reported": first["artifact_id"],
            "run_attempt_self_reported": first["run_attempt"],
            "nro_sha256": first["installed_nro_sha256"],
            "nro_size": first["installed_nro_size"],
        },
        "host_before_sd_baseline_sha256": baseline_sha256,
        "host_after_sd_readback_sha256": recheck_sha256,
        "readback_time_utc": after_time.isoformat(),
        "post_run_bundle_manifest_sha256": sha256_file(
            root / bundle.MANIFEST_NAME, 65536),
        "post_run_operator_sha256": sha256_file(observations, operator.MAX_INPUT_BYTES),
        "scenarios": analysis["acceptance_matrix"],
        "device_session_claims": card_rows,
        "chronology_findings": chronology,
        "handoff_result": analysis["result"],
        "handoff_followups": analysis["handoff_followups"],
        "self_reported_session_independence": "NOT_ATTESTED",
        "physical_switch_execution": "NOT_ATTESTED",
        "audible_music": "NOT_ATTESTED",
        "limitations": (
            "Pre-run manifest identity is intentionally NOT equated to the "
            "post-run manifest, which now includes raw CSV files. The same "
            "NRO SHA, full Git commit, CI run URL, and reported session "
            "chronology are checked; all observer dates and hardware claims "
            "remain unsigned. This is not device PASS or SD durability proof."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--cards-dir", required=True, type=Path)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--baseline-sha256", required=True)
    parser.add_argument("--recheck-report", required=True, type=Path)
    parser.add_argument("--recheck-sha256", required=True)
    parser.add_argument("--require-h06", action="store_true")
    parser.add_argument("--compare-builds", action="store_true")
    args = parser.parse_args(argv)
    try:
        out = link(args.bundle, args.observations, args.cards_dir,
                   args.baseline, args.baseline_sha256,
                   args.recheck_report, args.recheck_sha256,
                   require_h06=args.require_h06,
                   compare_builds=args.compare_builds)
    except (LinkError, reinsert.ReinsertError, handoff.HandoffError,
            operator.OperatorError, bundle.BundleError, audio.LogFormatError,
            OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
