#!/usr/bin/env python3
"""Compare groups of Switch NRO audio diagnostic CSVs, completely offline.

Usage:
    python3 tools/compare_switch_audio_sessions.py \
      --baseline old1.csv old2.csv --candidate new1.csv new2.csv
    python3 tools/compare_switch_audio_sessions.py --format json \
      --baseline old1.csv old2.csv --candidate new1.csv new2.csv

The last 128 retained snapshots are only a *window*. Counters are
cumulative: the first retained value is a baseline, not an incident.
Comparison is observational, not statistically conclusive and not an
actual test of physical speaker onset or audio fidelity. Device errors
are exposure-normalized (PCM per 10000 completed pages; HOME failures
per 100 resume events). A missing denominator is NOT treated as zero.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import analyze_switch_audio_log as audio

MIN_SESSIONS = 2
MIN_PAGES_PER_SESSION = 1000
MIN_HOME_EVENTS_PER_GROUP = 10
MIN_LATENCY_SAMPLES_PER_GROUP = 10
FAULT_MIN_TOTAL = 3
FAULT_RATE_ADDITIVE = 0.5
FAULT_RATE_MULTIPLIER = 1.5
LATENCY_MIN_INCREASE_US = 20_000
LATENCY_MULTIPLIER = 1.5


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def _latencies(rows: list[dict]) -> list[int]:
    samples = []
    for old, new in zip(rows, rows[1:]):
        if (new["first_pcm_count"] >= old["first_pcm_count"] + 1
                and new["last_pcm_us"] > 0):
            samples.append(int(new["last_pcm_us"]))
    return samples


def group(paths: list[Path]) -> dict:
    sessions = []
    totals = {name: 0 for name in (
        "output_pages", "home_resumes", "pcm_fail", "home_fail",
        "lease_fail", "pcm_recover", "home_recover", "pcm_restart",
        "home_reopen", "first_pcm_count")}
    latencies = []
    missing_individual_latency = 0
    gap_sessions = 0
    problems = []
    for path in paths:
        rows = audio.load_csv(path)
        report = audio.summarize(rows)
        gap_sessions += int(report["historical_gaps"] > 0)
        inc = report["observed_counter_increments"]
        for name in totals:
            totals[name] += inc[name]
        latencies.extend(_latencies(rows))
        missing_individual_latency += report["ack_latency_us"]["missing_individual_samples"]
        quality_issues = []
        if len(rows) < 2:
            quality_issues.append("only one retained snapshot")
        if inc["output_pages"] < MIN_PAGES_PER_SESSION:
            quality_issues.append(f"fewer than {MIN_PAGES_PER_SESSION} observed PCM pages")
        if report["time_rollbacks"]:
            quality_issues.append("clock rollback")
        if report["historical_gaps"]:
            quality_issues.append(
                "historical GAP: missing incident timing in evicted rows")
        if report["counter_rollbacks"]:
            quality_issues.append("counter rollback")
        if rows[-1]["event"] != "EXIT":
            quality_issues.append("missing EXIT marker")
        if quality_issues:
            problems.append({"file": str(path), "reasons": quality_issues})
        sessions.append({
            "file": str(path),
            "rows": len(rows),
            "retained_start_ms": rows[0]["elapsed_ms"],
            "retained_end_ms": rows[-1]["elapsed_ms"],
            "window_begins_at_session_start": rows[0]["event"] == "START",
            "window_exits_cleanly": rows[-1]["event"] == "EXIT",
            "pages": inc["output_pages"],
            "home_resumes": inc["home_resumes"],
            "pcm_fail": inc["pcm_fail"],
            "home_fail": inc["home_fail"],
            "lease_fail": inc["lease_fail"],
            "latency_samples": len(_latencies(rows)),
            "assessment": report["assessment"],
        })
    if len(paths) < MIN_SESSIONS:
        problems.append({
            "group": "cohort",
            "reasons": [f"need at least {MIN_SESSIONS} separate sessions"]
        })
    return {
        "sessions": sessions,
        "count": len(sessions),
        "counters": totals,
        "quality_problems": problems,
        "latency": {
            "sample_count": len(latencies),
            "missing_individual_samples": missing_individual_latency,
            "median_us": _percentile(latencies, .5),
            "p95_us": _percentile(latencies, .95),
            "max_observed_us": max(latencies) if latencies else None,
        },
        "truncated_windows": sum(not x["window_begins_at_session_start"]
                                 for x in sessions),
        "historical_gaps": gap_sessions,
    }


def _rate(value: int, exposure: int, scale: int) -> float | None:
    return round(value * scale / exposure, 6) if exposure > 0 else None


def compare(baseline: dict, candidate: dict) -> dict:
    bc, cc = baseline["counters"], candidate["counters"]
    reasons = []
    warnings = []
    metrics = {}
    valid = not baseline["quality_problems"] and not candidate["quality_problems"]
    if not valid:
        reasons.append("At least one cohort has insufficient or inconsistent retained data.")
    if baseline["truncated_windows"] or candidate["truncated_windows"]:
        warnings.append("Some sessions retain only the end of gameplay; historical events are unavailable.")
    if baseline["historical_gaps"] or candidate["historical_gaps"]:
        warnings.append("Historical GAP contains aggregated faults with unknown timing; comparison is inconclusive.")
    if cc["home_resumes"] < MIN_HOME_EVENTS_PER_GROUP or bc["home_resumes"] < MIN_HOME_EVENTS_PER_GROUP:
        warnings.append("Insufficient observed HOME events for comparative HOME failure rates.")
    elif valid and (
        cc["home_resumes"] * bc["output_pages"] > 3 * bc["home_resumes"] * cc["output_pages"]
        or bc["home_resumes"] * cc["output_pages"] > 3 * cc["home_resumes"] * bc["output_pages"]
    ):
        warnings.append("HOME frequency differs by more than 3x per completed PCM page.")
    if baseline["latency"]["sample_count"] < MIN_LATENCY_SAMPLES_PER_GROUP or candidate["latency"]["sample_count"] < MIN_LATENCY_SAMPLES_PER_GROUP:
        warnings.append("Insufficient individual completed-buffer latency samples for p95 comparison.")
    if baseline["latency"]["missing_individual_samples"] or candidate["latency"]["missing_individual_samples"]:
        warnings.append("Some confirmed buffers have no individual latency sample; p95 can be biased.")
    failures = []
    for name in ("pcm_fail", "lease_fail", "home_fail"):
        if name == "home_fail":
            exposure = "home_resumes"
            scale = 100
            sufficient = (
                bc[exposure] >= MIN_HOME_EVENTS_PER_GROUP and
                cc[exposure] >= MIN_HOME_EVENTS_PER_GROUP
            )
        else:
            exposure = "output_pages"
            scale = 10000
            sufficient = bc[exposure] > 0 and cc[exposure] > 0
        base_rate = _rate(bc[name], bc[exposure], scale)
        new_rate = _rate(cc[name], cc[exposure], scale)
        significant = (
            valid and sufficient and
            cc[name] >= FAULT_MIN_TOTAL and
            new_rate >= max(base_rate * FAULT_RATE_MULTIPLIER,
                            base_rate + FAULT_RATE_ADDITIVE)
        )
        metrics[name] = {
            "exposure": exposure,
            "scale": scale,
            "baseline_count": bc[name],
            "candidate_count": cc[name],
            "baseline_rate": base_rate,
            "candidate_rate": new_rate,
            "comparable": valid and sufficient,
            "regression_flag": significant,
        }
        if significant:
            failures.append(name)
    base_lat = baseline["latency"]["p95_us"]
    new_lat = candidate["latency"]["p95_us"]
    latency_comparable = (
        valid and base_lat is not None and new_lat is not None and
        baseline["latency"]["sample_count"] >= MIN_LATENCY_SAMPLES_PER_GROUP
        and candidate["latency"]["sample_count"] >= MIN_LATENCY_SAMPLES_PER_GROUP
    )
    latency_flag = (
        latency_comparable and
        new_lat >= max(base_lat * LATENCY_MULTIPLIER,
                       base_lat + LATENCY_MIN_INCREASE_US)
    )
    metrics["ack_latency_p95_us"] = {
        "baseline": base_lat,
        "candidate": new_lat,
        "baseline_samples": baseline["latency"]["sample_count"],
        "candidate_samples": candidate["latency"]["sample_count"],
        "comparable": latency_comparable,
        "regression_flag": latency_flag,
    }
    if latency_flag:
        failures.append("ack_latency_p95_us")
    if not valid:
        verdict = "INCONCLUSIVE"
    elif failures:
        verdict = "POTENTIAL_REGRESSION"
    else:
        verdict = "NO_REGRESSION_FLAG"
    return {
        "verdict": verdict,
        "flags": failures,
        "baseline": baseline,
        "candidate": candidate,
        "metrics": metrics,
        "reasons": reasons,
        "warnings": warnings,
        "criteria": {
            "minimum_sessions_per_cohort": MIN_SESSIONS,
            "minimum_completed_pages_per_session": MIN_PAGES_PER_SESSION,
            "minimum_home_events_per_cohort": MIN_HOME_EVENTS_PER_GROUP,
            "minimum_latency_samples_per_cohort": MIN_LATENCY_SAMPLES_PER_GROUP,
            "minimum_candidate_faults_for_flag": FAULT_MIN_TOTAL,
            "fault_rate_multiplier": FAULT_RATE_MULTIPLIER,
            "fault_rate_additive_per_exposure": FAULT_RATE_ADDITIVE,
            "p95_latency_multiplier": LATENCY_MULTIPLIER,
            "p95_latency_minimum_increase_us": LATENCY_MIN_INCREASE_US,
        },
        "scope": "Observed last 128 snapshots per CSV only; descriptive heuristics, not statistical significance or Switch speaker measurements.",
    }


def format_text(report: dict) -> str:
    lines = [
        "VANDAL HEARTS SWITCH AUDIO — NRO COHORT COMPARISON",
        f"Verdict: {report['verdict']} (heuristic; not a physical playback certification)",
        f"Baseline: {report['versions']['baseline']} ({report['baseline']['count']} sessions)",
        f"Candidate: {report['versions']['candidate']} ({report['candidate']['count']} sessions)",
        f"PCM pages observed: {report['baseline']['counters']['output_pages']} -> "
        f"{report['candidate']['counters']['output_pages']}",
    ]
    for name, metric in report["metrics"].items():
        if name == "ack_latency_p95_us":
            lines.append("Ack latency p95: "
                         f"{metric['baseline']} -> {metric['candidate']} us "
                         f"(samples {metric['baseline_samples']} -> "
                         f"{metric['candidate_samples']})"
                         + (" [FLAG]" if metric["regression_flag"] else ""))
        else:
            suffix = f"per {metric['scale']} {metric['exposure']}"
            lines.append(
                f"{name}: {metric['baseline_rate']} -> "
                f"{metric['candidate_rate']} {suffix} "
                f"(counts {metric['baseline_count']} -> {metric['candidate_count']})"
                + (" [INSUFFICIENT]" if not metric["comparable"] else
                   " [FLAG]" if metric["regression_flag"] else "")
            )
    lines.extend("REASON: " + r for r in report["reasons"])
    lines.extend("NOTE: " + r for r in report["warnings"])
    lines.append("Only the retained telemetry window is comparable. Listen on a real Switch before hardware claims.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, nargs="+", required=True,
                        help="older NRO session CSVs (at least two recommended)")
    parser.add_argument("--candidate", type=Path, nargs="+", required=True,
                        help="newer NRO session CSVs (at least two recommended)")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--baseline-version", default="unspecified",
                        help="optional local NRO version/commit label")
    parser.add_argument("--candidate-version", default="unspecified",
                        help="optional local NRO version/commit label")
    args = parser.parse_args(argv)
    old_paths = [p.resolve() for p in args.baseline]
    new_paths = [p.resolve() for p in args.candidate]
    if set(old_paths).intersection(new_paths):
        parser.error("same CSV must not be used in both groups")
    if len(set(old_paths)) != len(old_paths) or len(set(new_paths)) != len(new_paths):
        parser.error("duplicate CSV within one cohort is not a separate session")
    try:
        result = compare(group(args.baseline), group(args.candidate))
        result["versions"] = {
            "baseline": args.baseline_version,
            "candidate": args.candidate_version,
        }
    except audio.LogFormatError as exc:
        print(f"CSV validation failed: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(format_text(result))
    return 1 if result["verdict"] == "POTENTIAL_REGRESSION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
