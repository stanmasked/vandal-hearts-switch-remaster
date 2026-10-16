#!/usr/bin/env python3
"""Stage 215: offline, read-only Switch audio evidence triage.

The report analyzes verified NRO/CSV bundle bytes, not hardware audio.
It cannot tell HOME from sleep, prove independent console sessions, verify
speaker output or sign an operator's physical acceptance.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import analyze_switch_audio_log as audio
import verify_switch_audio_bundle as bundle

REPORT_SCHEMA = "vh-switch-audio-hardware-report/v1"
MANUAL_ONLY = "REQUIRES_MANUAL_HARDWARE_EVIDENCE"
FAILURES = ("pcm_fail", "home_fail", "lease_fail")


def review(bundle_dir: Path) -> dict:
    """Fail closed on a changed NRO, CSV, extra file or corrupt manifest."""
    integrity = bundle.inspect(bundle_dir)
    manifest = bundle.read_manifest(bundle_dir)
    sessions = []
    issues = []
    for entry in manifest["sessions"]:
        # inspect() has already checked every SHA and the CSV format.
        name = entry["path"]
        path = bundle.safe_member(bundle_dir, name, ".csv")
        stats = audio.summarize(audio.load_csv(path))
        increments = stats["observed_counter_increments"]
        faults = {name: increments[name] for name in FAILURES}
        pcm_faults = faults["pcm_fail"] + faults["lease_fail"]
        home_faults = faults["home_fail"]
        stalls = len(stats["possible_output_stalls"])
        missing_exit = stats["events"].get("EXIT", 0) == 0 or not (
            audio.load_csv(path)[-1]["event"] == "EXIT")
        if pcm_faults or home_faults or stats["error_status_entries"] or stalls:
            priority = "INVESTIGATE"
        elif (missing_exit or stats["counter_rollbacks"] or
              increments["output_pages"] < 1000 or stats["historical_gaps"]):
            priority = "INCONCLUSIVE"
        elif stats["assessment"] == "REVIEW" or stats["warnings"]:
            priority = "REVIEW"
        else:
            priority = "MANUAL_REVIEW_REQUIRED"
        issues.append(priority)
        sessions.append({
            "file": name,
            "sha256": entry["sha256"],
            "csv_rows": stats["rows"],
            "start_retained": stats["events"].get("START", 0) > 0,
            "end_exit": not missing_exit,
            "pcm": {
                "observed_pages": increments["output_pages"],
                "submit_failures": faults["pcm_fail"],
                "lease_failures": faults["lease_fail"],
                "restarts": increments["pcm_restart"],
                "recoveries": increments["pcm_recover"],
                "possible_stalls": stalls,
                "ack_latency_p95_us": stats["ack_latency_us"]["p95"],
                "ack_latency_sample_count": stats["ack_latency_us"]["recorded_samples"],
                "status_error_entries": stats["error_status_entries"],
            },
            "resume": {
                "observed_home_resumes": increments["home_resumes"],
                "home_failures": faults["home_fail"],
                "reopen_attempts": increments["home_reopen"],
                "recoveries": increments["home_recover"],
                "sleep_cycles": "NOT_SEPARATELY_OBSERVABLE",
            },
            "recording": {
                "historical_gaps": stats["historical_gaps"],
                "counter_rollbacks": stats["counter_rollbacks"],
                "unlocalized_faults": stats["unlocalized_faults"],
                "warnings": stats["warnings"],
                "observed_window_ms": stats["observed_elapsed_ms"],
            },
            "triage": priority,
        })
    if "INVESTIGATE" in issues:
        triage = "INVESTIGATE"
    elif (not sessions or integrity["telemetry_readiness"] == "INCOMPLETE" or
          "INCONCLUSIVE" in issues):
        triage = "INCONCLUSIVE"
    elif "REVIEW" in issues:
        triage = "REVIEW"
    else:
        triage = "MANUAL_REVIEW_REQUIRED"
    return {
        "schema": REPORT_SCHEMA,
        "hardware_status": bundle.HARDWARE_STATUS,
        "file_integrity": {
            "result": "VERIFIED_AGAINST_UNSIGNED_MANIFEST",
            "nro_structure": integrity["nro_structure"],
            "build_provenance": integrity["build_provenance"],
            "prior_sd_file_preservation": "NOT_OBSERVABLE",
            "power_loss_durability": "NOT_TESTED",
        },
        "build": {
            "git_sha_self_reported": manifest["git_sha"],
            "ci_run_url_self_reported": manifest["ci_run_url"],
            "nro": manifest["nro"],
        },
        "telemetry_readiness": integrity["telemetry_readiness"],
        "report_triage": triage,
        "session_count": len(sessions),
        "sessions": sessions,
        "duplicate_evidence_warnings": integrity["evidence_warnings"],
        "manual_acceptance": {
            "audible_quality": MANUAL_ONLY,
            "home_return_sound": MANUAL_ONLY,
            "sleep_resume_cycles": MANUAL_ONLY,
            "independent_physical_sessions": MANUAL_ONLY,
            "sd_prior_report_preservation": MANUAL_ONLY,
        },
        "limitations": (
            "Reports retained 128-row telemetry windows; counts are deltas only. "
            "A valid hash cannot prove an authentic build or physical Switch run. "
            "HOME counters do not distinguish physical sleep from normal resume. "
            "PCM acknowledgement latency is not acoustic latency. "
            "Only an independent operator can assign physical PASS."
        ),
    }


def cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def markdown(report: dict) -> str:
    lines = [
        "# Vandal Hearts Remake — Switch audio evidence triage (stage 215)",
        "",
        "**Hardware status: HARDWARE NOT TESTED.**",
        "",
        "This report is read-only telemetry review; it is NOT console acceptance.",
        "",
        f"- File integrity: {report['file_integrity']['result']}",
        f"- Build origin: {report['file_integrity']['build_provenance']}",
        f"- Telemetry readiness: {report['telemetry_readiness']}",
        f"- Review priority: {report['report_triage']}",
        f"- Sessions: {report['session_count']}",
        "",
        "| CSV session | PCM pages | PCM failures | Lease failures | HOME observed | HOME failures | EXIT | Priority |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for s in report["sessions"]:
        p, h = s["pcm"], s["resume"]
        lines.append("| " + " | ".join(map(cell, (
            s["file"], p["observed_pages"], p["submit_failures"],
            p["lease_failures"], h["observed_home_resumes"],
            h["home_failures"], s["end_exit"], s["triage"]
        ))) + " |")
    lines.extend([
        "",
        "## Evidence boundaries",
        "",
        "- File checks establish only matching bytes against a self-reported unsigned manifest.",
        "- Physical sleep cycles cannot be counted separately from HOME in current CSVs.",
        "- Prior SD file preservation and audible quality require external manual records.",
        "- A CSV records at most 128 recent snapshots; earlier incidents may have been evicted.",
        "- No automated result is a physical hardware PASS.",
    ])
    for warning in report["duplicate_evidence_warnings"]:
        lines.append("- WARNING: " + cell(warning))
    for s in report["sessions"]:
        lines.append("")
        lines.append("### " + cell(s["file"]))
        lines.append("- PCM: " + cell(s["pcm"]))
        lines.append("- HOME/resume: " + cell(s["resume"]))
        lines.append("- Recording: " + cell(s["recording"]))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        root = args.bundle.resolve()
        if not root.is_dir():
            raise bundle.BundleError("bundle directory not found")
        report = review(root)
    except (bundle.BundleError, audio.LogFormatError, OSError) as exc:
        print(f"INVALID EVIDENCE: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(markdown(report), end="")
    # Exit code zero signifies successful report *generation only*.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
