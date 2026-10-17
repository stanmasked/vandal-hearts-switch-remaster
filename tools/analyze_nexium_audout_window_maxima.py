#!/usr/bin/env python3
"""Stage 271: per-second MAXIMUM audoutPlayBuffer latency observations.

These are window maxima, NOT per-call histogram counts. One 50 ms
window asserts >=1 call reached 50 ms, never that every call did.
Never infer audible underruns, physical DAC starvation or Switch timing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

from audit_nexium_audout_repeatability import (
    MEMBERS, RepeatabilityError, compare, read_run,
)
from audit_nexium_audout_queue import HEADER, parse_telemetry

THRESHOLDS_US = (25_000, 40_000, 50_000)


def rank_nearest(values: list[int], percentile: float) -> int:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def individual_run(archive: Path) -> dict:
    evidence = read_run(archive)
    # read_run() first validates original/copy SHA-256 against the CSV
    # in the same ZIP and the original-SD audit from the workflow.
    with zipfile.ZipFile(archive) as zipped:
        csv_bytes = zipped.read(MEMBERS["csv"])
    if hashlib.sha256(csv_bytes).hexdigest() != evidence["queue_csv_sha256"]:
        raise RepeatabilityError("CSV changed after verified evidence read")
    # Parses and rechecks the complete full-session account before
    # deriving window statistics, even though the report is not about
    # the entire distribution of individual submit-call timings.
    parse_telemetry(csv_bytes)
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("ascii"), newline=""),
                               strict=True))
    if not rows or list(rows[0]) != HEADER:
        raise RepeatabilityError("unexpected canonical CSV column order")
    maxima = []
    windows = []
    for item in rows:
        if item["scope"] != "SECOND":
            continue
        number = int(item["second"])
        delay = int(item["max_call_us"])
        attempts = int(item["attempts"])
        if attempts <= 0:
            raise RepeatabilityError("empty window is not a timed submit sample")
        maxima.append(delay)
        windows.append({"second": number, "max_call_us": delay, "attempts": attempts})
    if (len(maxima) != evidence["audout_window_count"]
            or max(maxima) != evidence["audout_max_call_us"]
            or sum(x["attempts"] for x in windows) != evidence["audout_attempts"]
            or [x["second"] for x in windows] != list(range(len(windows)))):
        raise RepeatabilityError("window maxima and full-session report disagree")
    bands = [
        {"band": "<25ms", "window_count": sum(x < THRESHOLDS_US[0] for x in maxima)},
        {"band": "25-<40ms", "window_count": sum(THRESHOLDS_US[0] <= x < THRESHOLDS_US[1] for x in maxima)},
        {"band": "40-<50ms", "window_count": sum(THRESHOLDS_US[1] <= x < THRESHOLDS_US[2] for x in maxima)},
        {"band": ">=50ms", "window_count": sum(x >= THRESHOLDS_US[2] for x in maxima)},
    ]
    if sum(x["window_count"] for x in bands) != len(windows):
        raise RepeatabilityError("maxima histogram did not conserve windows")
    return {
        "run_id": evidence["run_id"],
        "run_attempt": evidence["run_attempt"],
        "git_sha": evidence["git_sha"],
        "nro_sha256": evidence["nro_sha256"],
        "csv_sha256": evidence["queue_csv_sha256"],
        "windows": len(windows),
        "audout_attempts": evidence["audout_attempts"],
        "max_window_us_min": min(maxima),
        "max_window_us_median_nearest_rank": rank_nearest(maxima, .5),
        "max_window_us_p90_nearest_rank": rank_nearest(maxima, .9),
        "max_window_us_p99_nearest_rank": rank_nearest(maxima, .99),
        "max_window_us_global": max(maxima),
        "windows_ge_40ms": sum(x >= 40_000 for x in maxima),
        "windows_ge_50ms": sum(x >= 50_000 for x in maxima),
        "seconds_with_max_ge_50ms": [x["second"] for x in windows if x["max_call_us"] >= 50_000],
        "window_maximum_bins": bands,
        "per_second_windows": windows,
    }


def analyze(archives: list[Path]) -> dict:
    compared = compare(archives)
    runs = sorted((individual_run(x) for x in archives),
                  key=lambda x: (x["run_id"], x["run_attempt"]))
    if [(x["run_id"], x["run_attempt"]) for x in runs] != [
            (x["run_id"], x["run_attempt"]) for x in compared["runs"]]:
        raise RepeatabilityError("runs changed across separate artifact reads")
    return {
        "schema": "vh-nexium-audout-window-maxima/v1",
        "result": "SAME_NRO_GUEST_WINDOW_MAXIMA_VERIFIED",
        "source_repeatability_result": compared["result"],
        "nro_sha256": compared["nro_sha256"],
        "run_count": len(runs),
        "runs": runs,
        "scope": "maximum blocking audoutPlayBuffer call in each guest-second window",
        "per_call_latency_distribution_known": False,
        "physical_hardware_tested": False,
        "audible_underruns_measured": False,
        "original_guest_sd_reopened_after_actions_run": False,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifact", type=Path, action="append", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.output.is_symlink() or args.output.exists():
            raise RepeatabilityError("refuse overwrite of prior analysis")
        report = analyze(args.artifact)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({"result": report["result"],
                          "run_count": report["run_count"],
                          "windows_ge_50ms": {
                              str(r["run_id"]): r["windows_ge_50ms"]
                              for r in report["runs"]
                          },
                          "hardware_tested": False}, sort_keys=True))
        return 0
    except (RepeatabilityError, OSError, ValueError, UnicodeError,
            csv.Error, zipfile.BadZipFile) as exc:
        print(json.dumps({"result": "GUEST_WINDOW_MAXIMA_NOT_VERIFIED",
                          "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
