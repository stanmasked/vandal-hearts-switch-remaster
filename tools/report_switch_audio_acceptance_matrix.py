#!/usr/bin/env python3
"""Stage 221: conservative H01-H07 hardware evidence matrix and retest checklist.

Offline, read-only; never certifies physical Switch tests. Source CSV is
verified against an unsigned manifest; operator observations are self-reported.
Exit 0 means a report was generated, NOT hardware approval.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import analyze_switch_audio_log as audio
import assess_switch_audio_first_run as first_run
import report_switch_audio_hardware as telemetry
import verify_switch_audio_bundle as bundle

SCHEMA = "vh-switch-audio-acceptance-matrix/v1"
READY = "MANUAL_CONFIRMATION_REQUIRED"
INCOMPLETE = "INCOMPLETE"
INVESTIGATE = "INVESTIGATE"
NOT_REQUIRED = "NOT_REQUIRED_FOR_THIS_REVIEW"
RETEST = {
    "H01": "Repeat two independent Switch launches, save distinct numbered CSV files, each with >=1000 observed PCM pages and a final EXIT; document sound and mode.",
    "H02": "Repeat and record >=10 physical HOME -> game returns with audible music; note each recovery and inspect home_fail/reopen counters.",
    "H03": "Repeat and record >=5 separate physical sleep -> wake cycles; verify audible playback after each. CSV HOME counter alone is insufficient.",
    "H04": "Repeat one continuously observed 30-60 minute music test, recording actual elapsed minutes, audible defects and PCM telemetry.",
    "H05": "After a later normal launch, independently hash the exact earlier CSV on SD and compare with its pre-launch hash and verified evidence copy.",
    "H06": "Only if safe and explicitly required: perform an isolated non-destructive export-failure test with no important data; preserve prior files.",
    "H07": "If comparing builds, capture >=2 independent verified CSV sessions per build under matching audio conditions; run the dedicated between-build comparator.",
}


def scenario(code: str, status: str, reason: str, observed: dict | None = None) -> dict:
    return {
        "id": code,
        "status": status,
        "reason": reason,
        "observed": observed or {},
        "next_action": RETEST[code] if status in (INCOMPLETE, INVESTIGATE) else None,
        "manual_confirmation": status == READY,
    }


def build_matrix(root: Path, observations: dict, *,
                 require_h06: bool = False,
                 compare_builds: bool = False) -> dict:
    """Never accepts caller-provided precomputed success/telemetry reports."""
    review = first_run.assess(root, observations)
    machine = telemetry.review(root)
    coverage = review["scenario_coverage"]
    findings = review["consistency_findings"]
    session_rows = review["sessions"]
    codes = {f["code"] for f in findings}
    per_session = machine["sessions"]
    file_warnings = machine["duplicate_evidence_warnings"]
    statuses = []
    matrix = []

    def add(code: str, status: str, why: str, observed: dict | None = None) -> None:
        statuses.append(status)
        matrix.append(scenario(code, status, why, observed))

    page_deficits = [
        {"csv": row["file"], "observed_pages": row["pcm"]["observed_pages"],
         "end_exit": row["end_exit"]}
        for row in per_session
        if row["pcm"]["observed_pages"] < 1000 or not row["end_exit"]
    ]
    bad_pcm = any(
        row["pcm"]["submit_failures"] or row["pcm"]["lease_failures"] or
        row["pcm"]["possible_stalls"] or row["pcm"]["status_error_entries"]
        for row in per_session)
    history_errors = "HISTORICAL_OR_RETAINED_ERROR" in codes
    exit_conflict = "CONTRADICTORY_EXIT" in codes
    operator_fails = any(
        row["operator_physical_switch"] == "NO" or
        row["operator_music_audible"] == "NO" or
        row["operator_artifacts"] == "HEARD" or
        row["operator_normal_exit"] == "NO"
        for row in session_rows)
    incomplete_operator = any(
        row["operator_physical_switch"] != "YES" or
        row["operator_music_audible"] != "YES" or
        row["operator_artifacts"] != "NONE" or
        row["operator_normal_exit"] != "YES"
        for row in session_rows) or any(
            row["launch_mode"] == "UNKNOWN" or row["audio_output"] == "UNKNOWN"
            for row in observations["sessions"])
    h01_data = {
        "session_count": len(session_rows),
        "two_distinct_csv_sufficient": coverage["H01_two_different_csv_1000_pages_each"],
        "insufficient_csv": page_deficits,
        "duplicate_evidence": bool(file_warnings),
    }
    if operator_fails or bad_pcm or history_errors or exit_conflict:
        add("H01", INVESTIGATE,
            "Operator reported an audio/exit fault or verified CSV contains an error/stall.",
            h01_data)
    elif not coverage["H01_two_different_csv_1000_pages_each"] or \
            incomplete_operator or file_warnings or \
            any(row["telemetry_triage"] == "INCONCLUSIVE" for row in session_rows):
        add("H01", INCOMPLETE,
            "Need two complete distinct CSV sessions and full manual startup/listening/exit observations.",
            h01_data)
    else:
        add("H01", READY,
            "CSV thresholds and operator claims are recorded; independence and audio remain to be witnessed.",
            h01_data)

    home_total = coverage["H02_home_operator_total"]
    home_errors = any(row["resume"]["home_failures"] for row in per_session)
    home_history = any(row["fault_counter_baseline"].get("home_fail", 0)
                       for row in session_rows)
    if home_errors or home_history or operator_fails:
        add("H02", INVESTIGATE,
            "Resume counter or operator-reported sound/exit problem needs cycle-level investigation.",
            {"operator_home_returns": home_total})
    elif home_total < 10 or "UNEXPLAINED_HOME_COUNTER" in codes or \
            incomplete_operator:
        add("H02", INCOMPLETE,
            "Ten observed HOME returns not consistently documented; CSV counters are not physical HOME events.",
            {"operator_home_returns": home_total})
    else:
        add("H02", READY,
            "Operator reported sufficient HOME returns; audible recovery remains manual-only.",
            {"operator_home_returns": home_total})

    sleep_total = coverage["H03_sleep_operator_total"]
    if operator_fails or home_errors or home_history:
        add("H03", INVESTIGATE,
            "Audio/exit or resume fault observed; isolate whether sleep or HOME caused it.",
            {"operator_sleep_cycles": sleep_total, "csv_sleep_cycles": "NOT_OBSERVABLE"})
    elif sleep_total < 5 or incomplete_operator:
        add("H03", INCOMPLETE,
            "Five physical sleep cycles not documented; HOME resumes do not identify sleep.",
            {"operator_sleep_cycles": sleep_total, "csv_sleep_cycles": "NOT_OBSERVABLE"})
    else:
        add("H03", READY,
            "Operator recorded sufficient sleep cycles; actual wake and audio behavior need manual confirmation.",
            {"operator_sleep_cycles": sleep_total, "csv_sleep_cycles": "NOT_OBSERVABLE"})

    minutes = coverage["H04_longest_operator_minutes"]
    if operator_fails or bad_pcm or history_errors:
        add("H04", INVESTIGATE,
            "A session has reported audio failure or observed PCM problem; long-run stability not demonstrated.",
            {"operator_longest_minutes": minutes})
    elif minutes < 30 or incomplete_operator:
        add("H04", INCOMPLETE,
            "Need a documented >=30 minute continuous physical listening session.",
            {"operator_longest_minutes": minutes})
    else:
        add("H04", READY,
            "Operator reported a long session; 128-row retained CSV cannot prove elapsed duration.",
            {"operator_longest_minutes": minutes})

    retention = coverage["H05_prior_csv_operator_hashes"]
    if retention in ("OPERATOR_HASHES_DIFFER", "PRIOR_CSV_HASH_CONTRADICTION"):
        add("H05", INVESTIGATE,
            "An earlier CSV changed or supplied hashes disagree with the verified copy.",
            {"retention": retention, "old_csv": coverage["H05_prior_csv_verified_path"]})
    elif retention != "FILE_BOUND_OPERATOR_HASHES_MATCH":
        add("H05", INCOMPLETE,
            "Old CSV SHA-256 must match before/after and be linked to the first verified session.",
            {"retention": retention, "old_csv": coverage["H05_prior_csv_verified_path"]})
    else:
        add("H05", READY,
            "File-bound operator hashes agree; independent SD readbacks still unverified.",
            {"retention": retention, "old_csv": coverage["H05_prior_csv_verified_path"],
             "independent_sd_readback": "NOT_ATTESTED"})

    if require_h06:
        add("H06", INCOMPLETE,
            "No verified safe isolated export-failure record is available; never simulate by cutting power.",
            {"export_fault_test": "NOT_ASSESSED", "safety": "NO_POWER_CUT"})
    else:
        add("H06", NOT_REQUIRED,
            "Optional destructive-risk scenario excluded from ordinary first-run review; host faults are not hardware evidence.",
            {"export_fault_test": "NOT_ASSESSED"})

    if compare_builds:
        add("H07", INCOMPLETE,
            "Only one build bundle is supplied; no independently verified two-build comparison can be inferred.",
            {"between_build_comparison": "NOT_PROVIDED"})
    else:
        add("H07", NOT_REQUIRED,
            "Between-build regression claim was not requested for this single-build review.",
            {"between_build_comparison": "NOT_REQUESTED"})

    if INVESTIGATE in statuses:
        priority = "INVESTIGATE"
    elif INCOMPLETE in statuses:
        priority = "INCONCLUSIVE"
    else:
        priority = "READY_FOR_INDEPENDENT_MANUAL_REVIEW"
    needs = [s for s in matrix if s["next_action"]]
    needs.sort(key=lambda row: (0 if row["status"] == INVESTIGATE else 1, row["id"]))
    return {
        "schema": SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "result": priority,
        "read_only": True,
        "build_git_sha_self_reported": review["build_git_sha"],
        "operator_record_schema": review["operator_record_schema"],
        "underlying_operator_review": review["result"],
        "underlying_csv_review": machine["report_triage"],
        "scenarios": matrix,
        "retests": [
            {"scenario": row["id"], "priority": row["status"],
             "action": row["next_action"], "reason": row["reason"]}
            for row in needs
        ],
        "unresolved_operator_findings": findings,
        "manual_gate": {
            "decision": "NEVER_AUTO_APPROVE",
            "independent_session_identity": "UNATTESTED",
            "listening_and_wake_observations": "SELF_REPORTED",
            "sd_survival": "OPERATOR_REPORTED_ONLY",
            "human_signoff_required": True,
        },
        "limitations": (
            "Scenarios describe sufficiency of recorded claims and bounded CSV "
            "telemetry; they do not verify any physical session. H06 and H07 "
            "cannot be passed by this single-build report. "
            "Code 0 means the report was created, not hardware PASS."
        ),
    }


def markdown(report: dict) -> str:
    def cell(x: object) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = [
        "# Vandal Hearts Remake — Stage 221 Hardware Review Matrix",
        "",
        "**HARDWARE NOT TESTED — automatic PASS prohibited.**",
        "",
        f"Review priority: **{cell(report['result'])}**",
        f"Build SHA (self-reported): \`{cell(report['build_git_sha_self_reported'])}\`",
        "",
        "| Scenario | Triage | Rationale |",
        "| --- | --- | --- |",
    ]
    for row in report["scenarios"]:
        lines.append("| " + " | ".join(map(cell, (
            row["id"], row["status"], row["reason"]))) + " |")
    lines += ["", "## Recommended re-tests (not yet performed)", ""]
    if not report["retests"]:
        lines.append("No machine-identified re-tests; independent manual hardware review is still required.")
    else:
        for row in report["retests"]:
            lines.append(f"- **{row['scenario']}** [{row['priority']}]: {cell(row['action'])}")
    lines += ["", "## Evidence limitations", "",
              "- Operator notes are self-reported; CSV covers only retained telemetry.",
              "- H06 failure injection must never use abrupt SD removal/power loss.",
              "- H07 comparisons require separate full bundles for each build.",
              "- No machine result confirms physical Nintendo Switch playback.",
              "- Manual reviewer, actual device log and signed decision are still required.",
              ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--observations", required=True, type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--require-h06", action="store_true",
                        help="show optional safe fault-injection evidence as required")
    parser.add_argument("--compare-builds", action="store_true",
                        help="require independent two-build H07 comparison evidence")
    args = parser.parse_args(argv)
    try:
        result = build_matrix(args.bundle.resolve(),
                              first_run.read_observations(args.observations),
                              require_h06=args.require_h06,
                              compare_builds=args.compare_builds)
    except (first_run.OperatorError, bundle.BundleError, audio.LogFormatError,
            OSError, TypeError, KeyError, ValueError) as exc:
        print(json.dumps({"result": "INVALID_EVIDENCE", "hardware_status": bundle.HARDWARE_STATUS,
                          "error": str(exc)}, indent=2, ensure_ascii=False))
        return 2
    if args.format == "markdown":
        print(markdown(result))
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
