#!/usr/bin/env python3
"""Stage 219: reconcile operator-recorded Switch audio observations with CSV.

Strictly offline/read-only. CSV proves only a bounded telemetry window.
Operator JSON is self-reported, not authenticated, and never grants a
physical hardware PASS. The tool does not modify any evidence or SD files.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import analyze_switch_audio_log as audio
import report_switch_audio_hardware as telemetry
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-first-run-operator/v1"
REPORT_SCHEMA = "vh-switch-audio-first-run-review/v1"
MAX_INPUT_BYTES = 64 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MODES = {"APPLICATION", "APPLET", "UNKNOWN"}
OUTPUTS = {"HANDHELD", "DOCK_HDMI", "HEADPHONES", "BLUETOOTH", "UNKNOWN"}
ANSWER = {"YES", "NO", "UNKNOWN"}
ARTIFACTS = {"NONE", "HEARD", "UNKNOWN"}
CHECKS = {"recorded", "incomplete", "investigate"}
SESSION_KEYS = {
    "id", "csv", "physical_switch", "launch_mode", "audio_output",
    "music_audible", "audio_artifacts", "home_returns", "sleep_resumes",
    "continuous_minutes", "normal_exit", "notes",
}
RECORD_KEYS = {"schema", "build_git_sha", "nro_sha256", "sessions",
               "prior_csv_sha256_before", "prior_csv_sha256_after"}


class OperatorError(ValueError):
    """Malformed, conflicting or untrustworthy operator input."""


def require(ok: bool, why: str) -> None:
    if not ok:
        raise OperatorError(why)


def read_observations(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(),
            "operator file missing or a symlink")
    require(path.stat().st_size <= MAX_INPUT_BYTES,
            "operator file exceeds 64 KiB")
    try:
        value = json.loads(path.read_text(encoding="utf-8"),
                           object_pairs_hook=bundle.unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OperatorError(f"invalid operator JSON: {exc}") from exc
    require(isinstance(value, dict) and set(value) == RECORD_KEYS,
            "operator JSON schema fields missing or unknown")
    require(value["schema"] == SCHEMA, "unsupported operator record schema")
    require(isinstance(value["build_git_sha"], str) and
            bool(re.fullmatch(r"[0-9a-f]{40}", value["build_git_sha"])),
            "invalid build SHA")
    require(isinstance(value["nro_sha256"], str) and
            bool(SHA256.fullmatch(value["nro_sha256"])), "invalid NRO SHA-256")
    require(isinstance(value["sessions"], list) and
            len(value["sessions"]) <= 64, "sessions must be a list of at most 64")
    for field in ("prior_csv_sha256_before", "prior_csv_sha256_after"):
        require(value[field] is None or
                (isinstance(value[field], str) and bool(SHA256.fullmatch(value[field]))),
                f"invalid {field}")
    require((value["prior_csv_sha256_before"] is None) ==
            (value["prior_csv_sha256_after"] is None),
            "before/after CSV SHA-256 must both be present or absent")
    identifiers = set()
    paths = set()
    for session in value["sessions"]:
        require(isinstance(session, dict) and set(session) == SESSION_KEYS,
                "session fields missing or unknown")
        ident, name = session["id"], session["csv"]
        require(isinstance(ident, str) and
                bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident)),
                "invalid operator session ID")
        require(isinstance(name, str) and len(name) <= 256,
                "invalid operator CSV path")
        require(ident not in identifiers and name not in paths,
                "repeated operator session ID or CSV path")
        identifiers.add(ident)
        paths.add(name)
        for field in ("physical_switch", "music_audible", "normal_exit"):
            require(session[field] in ANSWER and isinstance(session[field], str),
                    f"invalid {field}: use YES, NO or UNKNOWN")
        require(session["audio_artifacts"] in ARTIFACTS and
                isinstance(session["audio_artifacts"], str),
                "invalid audio_artifacts")
        require(session["launch_mode"] in MODES and
                isinstance(session["launch_mode"], str), "invalid launch_mode")
        require(session["audio_output"] in OUTPUTS and
                isinstance(session["audio_output"], str), "invalid audio_output")
        for field in ("home_returns", "sleep_resumes", "continuous_minutes"):
            count = session[field]
            require(count is None or
                    (type(count) is int and 0 <= count <= 10000),
                    f"invalid {field}: nonnegative integer or null")
        require(isinstance(session["notes"], str) and
                len(session["notes"]) <= 1024, "notes must be <=1024 characters")
    return value


def assess(root: Path, record: dict) -> dict:
    checked = bundle.inspect(root)
    manifest = bundle.read_manifest(root)
    require(record["build_git_sha"] == manifest["git_sha"] and
            record["nro_sha256"] == manifest["nro"]["sha256"],
            "operator record refers to another NRO/build")
    analysis = telemetry.review(root)
    indexed = {session["file"]: session for session in analysis["sessions"]}
    require(set(s["csv"] for s in record["sessions"]) == set(indexed),
            "operator CSV coverage must match complete immutable bundle")
    issues = []
    if checked["evidence_warnings"]:
        issues.append("Duplicate CSV bytes: independent sessions not demonstrated.")
    accepted = []
    max_minutes = 0
    home_total, sleep_total = 0, 0
    record_incomplete = False
    problem_seen = False
    for item in record["sessions"]:
        observed = indexed[item["csv"]]
        pcm, home = observed["pcm"], observed["resume"]
        # Retained CSV window is not a complete physical history. Never
        # assert equality between operator HOME count and journal increments.
        warnings = []
        if (item["physical_switch"] != "YES" or
                item["music_audible"] == "UNKNOWN" or
                item["audio_artifacts"] == "UNKNOWN" or
                item["normal_exit"] == "UNKNOWN" or
                item["launch_mode"] == "UNKNOWN" or
                item["audio_output"] == "UNKNOWN" or
                item["home_returns"] is None or
                item["sleep_resumes"] is None or
                item["continuous_minutes"] is None):
            record_incomplete = True
            warnings.append("Physical observations missing or not independently confirmed.")
        if (item["physical_switch"] == "NO" or
                item["music_audible"] == "NO" or
                item["audio_artifacts"] == "HEARD" or
                item["normal_exit"] == "NO"):
            problem_seen = True
            warnings.append("Operator reported a hardware/audio fault.")
        if pcm["submit_failures"] or pcm["lease_failures"] or home["home_failures"] or \
                pcm["status_error_entries"] or pcm["possible_stalls"]:
            problem_seen = True
            warnings.append("CSV contains observed PCM/HOME fault or potential stall.")
        if pcm["observed_pages"] < 1000 or not observed["end_exit"] or \
                observed["recording"]["counter_rollbacks"]:
            record_incomplete = True
            warnings.append("CSV does not satisfy H01 retained-window requirements.")
        if item["home_returns"] is not None:
            home_total += item["home_returns"]
        if item["sleep_resumes"] is not None:
            sleep_total += item["sleep_resumes"]
        if item["continuous_minutes"] is not None:
            max_minutes = max(max_minutes, item["continuous_minutes"])
        accepted.append({
            "id": item["id"], "csv": item["csv"],
            "operator_physical_switch": item["physical_switch"],
            "operator_music_audible": item["music_audible"],
            "operator_artifacts": item["audio_artifacts"],
            "operator_normal_exit": item["normal_exit"],
            "operator_home_returns": item["home_returns"],
            "csv_observed_home_increments": home["observed_home_resumes"],
            "operator_sleep_resumes": item["sleep_resumes"],
            "operator_continuous_minutes": item["continuous_minutes"],
            "csv_observed_pcm_pages": pcm["observed_pages"],
            "csv_exit_present": observed["end_exit"],
            "telemetry_triage": observed["triage"],
            "review_notes": warnings,
        })
    retention = "NOT_RECORDED"
    if record["prior_csv_sha256_before"] is not None:
        retention = ("OPERATOR_HASHES_MATCH" if
                     record["prior_csv_sha256_before"] ==
                     record["prior_csv_sha256_after"] else
                     "OPERATOR_HASHES_DIFFER")
        if retention == "OPERATOR_HASHES_DIFFER":
            problem_seen = True
            issues.append("Prior SD CSV before/after hashes differ; investigate corruption.")
    h01 = len(accepted) >= 2 and checked["telemetry_readiness"] == \
        "ENOUGH_DATA_FOR_MANUAL_REVIEW"
    h02 = home_total >= 10 and not record_incomplete
    h03 = sleep_total >= 5 and not record_incomplete
    h04 = max_minutes >= 30 and not record_incomplete
    if not h01 or not h02 or not h03 or not h04:
        record_incomplete = True
    if retention != "OPERATOR_HASHES_MATCH":
        record_incomplete = True
    if analysis["report_triage"] == "INVESTIGATE":
        problem_seen = True
    if problem_seen:
        overall = "INVESTIGATE"
    elif record_incomplete or analysis["report_triage"] == "INCONCLUSIVE":
        overall = "INCONCLUSIVE"
    else:
        overall = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"
    return {
        "schema": REPORT_SCHEMA,
        "result": overall,
        "hardware_status": bundle.HARDWARE_STATUS,
        "evidence": "CSV_HASH_VERIFIED_OPERATOR_OBSERVATIONS_UNATTESTED",
        "build_git_sha": manifest["git_sha"],
        "session_count": len(accepted),
        "sessions": accepted,
        "scenario_coverage": {
            "H01_two_different_csv_1000_pages_each": h01,
            "H02_home_operator_total": home_total,
            "H02_minimum_10_claimed": h02,
            "H03_sleep_operator_total": sleep_total,
            "H03_minimum_5_claimed": h03,
            "H04_longest_operator_minutes": max_minutes,
            "H04_minimum_30_claimed": h04,
            "H05_prior_csv_operator_hashes": retention,
            "H06_safe_export_failure": "NOT_ASSESSED",
            "H07_between_build_comparison": "NOT_ASSESSED",
        },
        "flags": issues,
        "limitations": (
            "Operator JSON and physical session independence are not authenticated. "
            "Retained 128-row CSV counters cannot prove all HOME/sleep cycles, "
            "audible quality, old SD CSV survival, or sustained playback duration. "
            "A READY report is NOT console PASS and needs a signed operator decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        output = assess(args.bundle.resolve(), read_observations(args.observations))
    except (OperatorError, bundle.BundleError, audio.LogFormatError,
            OSError, KeyError, TypeError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE",
                          "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
