#!/usr/bin/env python3
"""Stage 222: read-only final evidence inventory and session-repeatability audit.

A locally completed handoff is not hardware certification. Operator cards and
timestamps are unsigned claims; they cannot authenticate a physical Switch,
distinct launches, playback quality or SD durability. No source files are
rewritten, copied or uploaded.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import re
import sys
from pathlib import Path

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as first_run
import report_switch_audio_acceptance_matrix as matrix
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-handoff/v1"
CARD_SCHEMA = "vh-switch-audio-session-card/v1"
CARD_KEYS = {
    "schema", "session_id", "csv", "csv_sha256", "nro_sha256",
    "git_sha", "launch_id", "start_utc", "end_utc", "console_label",
    "launch_mode", "audio_output", "music_audible",
    "audio_artifacts", "normal_exit", "observer_note",
}
MAX_CARD = 32 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class HandoffError(ValueError):
    """Invalid metadata, unsafe path, or contradictory signed-off evidence."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise HandoffError(reason)


def parse_time(value: object) -> datetime:
    require(isinstance(value, str) and len(value) <= 40,
            "card requires a timezone-aware ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HandoffError("invalid session card timestamp") from exc
    require(result.tzinfo is not None and result.utcoffset() is not None,
            "session card timestamp must specify timezone")
    return result.astimezone(timezone.utc)


def read_card(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(),
            "session card is missing or a symlink")
    require(path.stat().st_size <= MAX_CARD, "session card exceeds 32 KiB")
    try:
        card = json.loads(path.read_text(encoding="utf-8"),
                          object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise HandoffError(f"invalid session card JSON: {exc}") from exc
    require(isinstance(card, dict) and set(card) == CARD_KEYS and
            card.get("schema") == CARD_SCHEMA, "invalid session card schema")
    for key in ("session_id", "launch_id", "console_label"):
        require(isinstance(card[key], str) and TOKEN.fullmatch(card[key]) is not None,
                f"invalid card {key}")
    require(isinstance(card["csv"], str) and 0 < len(card["csv"]) <= 256,
            "invalid card CSV path")
    for key in ("csv_sha256", "nro_sha256"):
        require(isinstance(card[key], str) and SHA256.fullmatch(card[key]) is not None,
                f"invalid card {key}")
    require(isinstance(card["git_sha"], str) and
            bundle.GIT_SHA_RE.fullmatch(card["git_sha"]) is not None,
            "invalid card git_sha")
    for key, values in (
        ("launch_mode", first_run.MODES),
        ("audio_output", first_run.OUTPUTS),
        ("music_audible", first_run.ANSWER),
        ("audio_artifacts", first_run.ARTIFACTS),
        ("normal_exit", first_run.ANSWER),
    ):
        require(isinstance(card[key], str) and card[key] in values,
                f"invalid card {key}")
    require(isinstance(card["observer_note"], str) and
            len(card["observer_note"]) <= 1024, "invalid observer note")
    start = parse_time(card["start_utc"])
    end = parse_time(card["end_utc"])
    require(start < end and end - start <= timedelta(hours=24),
            "card session timeline must have positive duration <=24h")
    return card


def inventory(path: Path, role: str, name: str) -> dict:
    require(path.is_file() and not path.is_symlink(),
            f"evidence file missing or symbolic link: {name}")
    size, digest = bundle.digest_file(path)
    return {"role": role, "name": name, "size": size, "sha256": digest}


def audit(root: Path, observations: Path, cards_dir: Path,
          *, require_h06: bool = False, compare_builds: bool = False) -> dict:
    root = root.resolve()
    require(root.is_dir(), "bundle directory missing")
    require(not observations.is_symlink() and observations.is_file(),
            "operator JSON missing or a symbolic link")
    require(not observations.resolve().is_relative_to(root),
            "operator JSON must be outside the immutable evidence bundle")
    require(not cards_dir.is_symlink(), "cards directory may not be a symlink")
    if cards_dir.exists():
        require(cards_dir.is_dir() and
                not cards_dir.resolve().is_relative_to(root),
                "cards directory must exist outside the evidence bundle")
    operator = first_run.read_observations(observations)
    reviewed = matrix.build_matrix(
        root, operator, require_h06=require_h06, compare_builds=compare_builds)
    manifest = bundle.read_manifest(root)
    require(reviewed["hardware_status"] == bundle.HARDWARE_STATUS,
            "upstream hardware status must stay untested")
    files = [
        inventory(root / bundle.MANIFEST_NAME, "unsigned_bundle_manifest",
                  bundle.MANIFEST_NAME),
        inventory(bundle.safe_member(root, manifest["nro"]["path"], ".nro"),
                  "nro", manifest["nro"]["path"]),
    ]
    for csv_entry in manifest["sessions"]:
        files.append(inventory(bundle.safe_member(root, csv_entry["path"], ".csv"),
                               "raw_csv", csv_entry["path"]))
    files.append(inventory(observations, "operator_claims",
                           observations.name))
    expected = {s["id"] + ".json" for s in operator["sessions"]}
    found = set()
    if cards_dir.is_dir():
        found = {p.name for p in cards_dir.iterdir()
                 if p.name.endswith(".json")}
    # Any unexpected JSON is a potential accidental session substitution.
    require(not found.difference(expected),
            "untracked extra session-card JSON in cards directory")
    missing = []
    contradictions = []
    validated = []
    launch_ids = set()
    seen_console = set()
    previous_end = None
    session_records = []
    for item in operator["sessions"]:
        card_name = item["id"] + ".json"
        path = cards_dir / card_name
        if not path.exists():
            missing.append(item["id"])
            session_records.append({"id": item["id"], "card": card_name,
                                    "status": "MISSING_MANUAL_CARD"})
            continue
        card = read_card(path)
        files.append(inventory(path, "self_reported_session_card", card_name))
        failures = []
        if card["session_id"] != item["id"] or card["csv"] != item["csv"]:
            failures.append("CARD_SESSION_ID_OR_CSV_MISMATCH")
        csv_by_path = {x["path"]: x for x in manifest["sessions"]}
        entry = csv_by_path[item["csv"]]
        if (card["csv_sha256"] != entry["sha256"] or
                card["nro_sha256"] != manifest["nro"]["sha256"] or
                card["git_sha"] != manifest["git_sha"]):
            failures.append("CARD_BINARY_OR_CSV_IDENTITY_MISMATCH")
        for key in ("launch_mode", "audio_output", "music_audible",
                    "audio_artifacts", "normal_exit"):
            if card[key] != item[key]:
                failures.append("CARD_OPERATOR_" + key.upper() + "_DISAGREEMENT")
        if card["launch_id"] in launch_ids:
            failures.append("DUPLICATE_SELF_REPORTED_LAUNCH_ID")
        launch_ids.add(card["launch_id"])
        start, end = parse_time(card["start_utc"]), parse_time(card["end_utc"])
        if previous_end is not None and start <= previous_end:
            failures.append("OVERLAPPING_OR_OUT_OF_ORDER_LAUNCHES")
        previous_end = end
        minutes = item["continuous_minutes"]
        if minutes is not None and (
                timedelta(minutes=minutes) > end - start):
            failures.append("REPORTED_CONTINUOUS_MINUTES_EXCEED_CARD_DURATION")
        seen_console.add(card["console_label"])
        if (card["music_audible"] == "UNKNOWN" or
                card["audio_artifacts"] == "UNKNOWN" or
                card["normal_exit"] == "UNKNOWN"):
            failures.append("CARD_AUDIO_OBSERVATION_UNKNOWN")
        if failures:
            contradictions.extend({"session": item["id"], "code": code}
                                  for code in failures)
        validated.append({"id": item["id"], "launch_id": card["launch_id"],
                          "console_label": card["console_label"],
                          "begin": start.isoformat(), "end": end.isoformat()})
        session_records.append({
            "id": item["id"], "card": card_name,
            "status": "SELF_REPORTED_CARD_RECORDED" if not failures else
                      "CONTRADICTORY_CARD", "issues": failures,
        })
    # A group can be structurally distinct without being physically independent.
    unique_runs = len(validated) >= 2 and len(launch_ids) == len(validated)
    consistency = (len(validated) >= 2 and unique_runs and
                   len(seen_console) == 1 and not missing and not contradictions)
    if len(seen_console) > 1:
        contradictions.append({"session": None,
                               "code": "DIFFERENT_CONSOLE_LABELS"})
    if contradictions or reviewed["result"] == "INVESTIGATE":
        result = "INVESTIGATE"
    elif missing or not consistency or reviewed["result"] == "INCONCLUSIVE":
        result = "INCONCLUSIVE"
    else:
        result = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"

    additional = []
    if missing:
        additional.append({"priority": "INCOMPLETE",
                           "action": "Fill one original dated operator card per independent physical NRO launch.",
                           "missing_sessions": missing})
    if contradictions:
        additional.append({"priority": "INVESTIGATE",
                           "action": "Reconcile card identity, chronology and output with original CSV and written session notes.",
                           "codes": sorted({x["code"] for x in contradictions})})
    if not unique_runs:
        additional.append({"priority": "INCOMPLETE",
                           "action": "Provide at least two distinctly identified, non-overlapping operator-recorded NRO launches."})
    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "result": result,
        "build": {
            "git_sha_self_reported": manifest["git_sha"],
            "ci_run_url_self_reported": manifest["ci_run_url"],
            "nro_sha256": manifest["nro"]["sha256"],
            "nro_size": manifest["nro"]["size"],
        },
        "source_inventory": files,
        "session_cards": session_records,
        "repeated_session_claims": {
            "listed": len(operator["sessions"]),
            "cards_present": len(validated),
            "unique_launch_ids": unique_runs,
            "single_console_label": len(seen_console) == 1,
            "timestamps_nonoverlap": not any(
                f["code"] == "OVERLAPPING_OR_OUT_OF_ORDER_LAUNCHES"
                for f in contradictions),
            "self_report_consistent": consistency,
            "physical_independence": "NOT_ATTESTED",
        },
        "acceptance_matrix": reviewed["scenarios"],
        "retests": reviewed["retests"],
        "handoff_followups": additional,
        "contradictions": contradictions,
        "manual_signoff": "REQUIRED_NOT_AUTOMATED",
        "limitations": (
            "Each file hash is measured locally. The operator cards, launch IDs, "
            "dates and console label are self-reported and not signed evidence of "
            "a physical session. Host-side source checks cannot attest GitHub "
            "provenance, SD durability, audio audibility or physical independence. "
            "An all-consistent handoff is NOT hardware PASS."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--cards-dir", type=Path, required=True)
    parser.add_argument("--require-h06", action="store_true")
    parser.add_argument("--compare-builds", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = audit(args.bundle, args.observations, args.cards_dir,
                       require_h06=args.require_h06,
                       compare_builds=args.compare_builds)
    except (HandoffError, first_run.OperatorError, bundle.BundleError,
            audio.LogFormatError, OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
