#!/usr/bin/env python3
"""Offline analysis of the bounded audio-diagnostics.csv emitted by Switch.

Read-only, standard library only; no console connection or game assets.
A ring journal preserves at most 128 *recent* snapshots. Every cumulative
counter's first value is a baseline, NOT an observed event in this window.
No CSV timestamp or PCM service acknowledgement proves audible latency.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

COLUMNS = (
    "elapsed_ms", "event", "status", "home_resumes", "first_pcm_count",
    "last_pcm_us", "worst_pcm_us", "output_pages", "output_frames",
    "pcm_fail", "pcm_restart", "pcm_recover", "home_fail", "home_reopen",
    "home_recover", "lease_fail", "lease_reset", "vab_warn",
)
EVENTS = {"START", "PERIODIC", "STATE", "RESUME", "ERROR", "EXIT", "CLOCK", "GAP"}
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1
ROWS_LIMIT = 128
BYTES_LIMIT = 128 * 1024
COUNTERS = tuple(c for c in COLUMNS if c not in ("elapsed_ms", "event", "status"))
FAULTS = ("pcm_fail", "home_fail", "lease_fail")
CLUSTER_MS = 60_000
STALL_MS = 10_000


class LogFormatError(ValueError):
    """Malformed, truncated or non-Switch audio journal."""


def _number(raw: str, col: str, row: int) -> int:
    signed = col == "status"
    if not raw or (raw[0] == "-" and signed and
                   raw[1:].isascii() and raw[1:].isdigit()):
        if not raw:
            raise LogFormatError(f"row {row}: empty {col}")
        n = int(raw)
    elif raw.isascii() and raw.isdigit():
        n = int(raw)
    else:
        raise LogFormatError(f"row {row}: invalid integer {col}")
    maximum = (1 << 31) - 1 if signed else (U64 if col in (
        "elapsed_ms", "last_pcm_us", "worst_pcm_us",
        "output_pages", "output_frames") else U32)
    minimum = -(1 << 31) if signed else 0
    if not minimum <= n <= maximum:
        raise LogFormatError(f"row {row}: out-of-range {col}")
    return n


def load_csv(path: Path) -> list[dict[str, int | str]]:
    try:
        if path.stat().st_size > BYTES_LIMIT:
            raise LogFormatError("file too large for a 128-row journal")
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            csv.field_size_limit(128)
            reader = csv.reader(f, strict=True)
            if tuple(next(reader, ())) != COLUMNS:
                raise LogFormatError("unexpected CSV header or column order")
            rows: list[dict[str, int | str]] = []
            for row_no, values in enumerate(reader, start=2):
                if len(rows) == ROWS_LIMIT:
                    raise LogFormatError("more than 128 exported journal rows")
                if len(values) != len(COLUMNS):
                    raise LogFormatError(f"row {row_no}: expected {len(COLUMNS)} fields")
                row = {k: (v if k == "event" else _number(v, k, row_no))
                       for k, v in zip(COLUMNS, values)}
                if row["event"] not in EVENTS:
                    raise LogFormatError(f"row {row_no}: unknown event")
                if rows and row["elapsed_ms"] < rows[-1]["elapsed_ms"] and row["event"] != "CLOCK":
                    raise LogFormatError(f"row {row_no}: backward time without CLOCK event")
                rows.append(row)
            if not rows:
                raise LogFormatError("journal has no measurements")
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise LogFormatError(str(exc)) from exc


def summarize(rows: list[dict[str, int | str]]) -> dict:
    first, last = rows[0], rows[-1]
    increments: dict[str, int] = {k: 0 for k in COUNTERS}
    resets: dict[str, int] = {k: 0 for k in COUNTERS}
    errors: list[dict[str, int | str]] = []
    latency: list[int] = []
    unobserved_latency = 0
    clock_events = 0
    gaps = 0
    unlocalized_faults: dict[str, int] = {name: 0 for name in FAULTS}
    possible_stalls: list[dict[str, int]] = []
    error_entries = int(first["status"] < 0)
    last_worst = 0
    for prev, cur in zip(rows, rows[1:]):
        delta: dict[str, int] = {}
        if cur["elapsed_ms"] < prev["elapsed_ms"]:
            clock_events += 1
        if cur["event"] == "GAP":
            gaps += 1
        for key in COUNTERS:
            before, after = prev[key], cur[key]
            assert isinstance(before, int) and isinstance(after, int)
            if after < before:
                resets[key] += 1
                delta[key] = 0
            else:
                delta[key] = after - before
                increments[key] += delta[key]
        if cur["status"] < 0 and prev["status"] >= 0:
            error_entries += 1
        if delta["first_pcm_count"]:
            if cur["event"] != "GAP" and cur["last_pcm_us"] > 0:
                latency.append(int(cur["last_pcm_us"]))
            # GAP contains aggregated counter changes from events
            # whose timing and individual latency are gone forever.
            unobserved_latency += delta["first_pcm_count"] - int(
                cur["event"] != "GAP" and cur["last_pcm_us"] > 0)
        if (cur["elapsed_ms"] >= prev["elapsed_ms"] and
            cur["elapsed_ms"] - prev["elapsed_ms"] >= STALL_MS and
            cur["status"] == prev["status"] == 1 and
            cur["event"] != "GAP" and
            delta["output_pages"] == 0):
            possible_stalls.append({
                "start_ms": prev["elapsed_ms"],
                "end_ms": cur["elapsed_ms"],
            })
        for key in FAULTS:
            if delta[key]:
                if cur["event"] == "GAP":
                    unlocalized_faults[key] += delta[key]
                else:
                    errors.append({
                        "at_ms": cur["elapsed_ms"],
                        "kind": key,
                        "increments": delta[key],
                        "segment": clock_events + gaps,
                    })
        last_worst = max(last_worst, int(cur["worst_pcm_us"]))
    last_worst = max(last_worst, int(first["worst_pcm_us"]))

    clusters: list[dict] = []
    for error in errors:
        if (clusters and error["segment"] == clusters[-1]["segment"] and
            error["at_ms"] >= clusters[-1]["end_ms"] and
            error["at_ms"] - clusters[-1]["end_ms"] <= CLUSTER_MS):
            cluster = clusters[-1]
            cluster["end_ms"] = error["at_ms"]
            cluster["total_increments"] += error["increments"]
            cluster["kinds"][error["kind"]] = (
                cluster["kinds"].get(error["kind"], 0) + error["increments"])
        else:
            clusters.append({
                "start_ms": error["at_ms"],
                "end_ms": error["at_ms"],
                "segment": error["segment"],
                "total_increments": error["increments"],
                "kinds": {error["kind"]: error["increments"]},
            })
    repeats = [c for c in clusters if c["total_increments"] >= 2]
    latency.sort()
    max_latency = max(latency) if latency else None
    p95 = latency[math.ceil(0.95 * len(latency)) - 1] if latency else None
    time_spans = [max(0, int(b["elapsed_ms"]) - int(a["elapsed_ms"]))
                  for a, b in zip(rows, rows[1:])]
    warnings: list[str] = []
    if first["event"] != "START":
        warnings.append("Beginning of the session is not present in the ring buffer.")
    if gaps:
        warnings.append(
            "Historical GAP: oldest incident timestamps were evicted, "
            "but cumulative fault counts remain visible. "
            "Faults across the GAP must not be assigned to the boundary timestamp."
        )
    if last["event"] != "EXIT":
        warnings.append("No EXIT row; this might be a partial export.")
    if clock_events:
        warnings.append("Elapsed-time rollback detected; wall duration is ambiguous.")
    if any(resets.values()):
        warnings.append("One or more cumulative counters decreased; increments across resets are unknown.")
    if increments["first_pcm_count"] > len(latency):
        warnings.append("Not every confirmed buffer has its own retained latency sample.")
    if possible_stalls:
        warnings.append("Possible output stalls; sparse snapshots cannot prove a device hang.")
    if int(last["vab_warn"]) > 0:
        warnings.append("VAB fallback warnings recorded; timbre fidelity is not confirmed.")
    if max_latency is not None and max_latency > 100_000:
        warnings.append("Some completed-buffer acknowledgements exceeded 100 ms.")
    if errors or any(unlocalized_faults.values()) or error_entries or possible_stalls:
        severity = "INVESTIGATE"
    elif clock_events or any(resets.values()) or max_latency is not None and max_latency > 50_000:
        severity = "REVIEW"
    else:
        severity = "NO_OBSERVED_FAULTS"
    return {
        "assessment": severity,
        "rows": len(rows),
        "time_start_ms": first["elapsed_ms"],
        "time_end_ms": last["elapsed_ms"],
        "observed_elapsed_ms": sum(time_spans) if not clock_events else None,
        "time_rollbacks": clock_events,
        "historical_gaps": gaps,
        "unlocalized_faults": unlocalized_faults,
        "events": dict(sorted(Counter(str(r["event"]) for r in rows).items())),
        "starting_status": first["status"],
        "ending_status": last["status"],
        "error_status_entries": error_entries,
        "observed_counter_increments": increments,
        "counter_rollbacks": {k: v for k, v in resets.items() if v},
        "fault_clusters_60s": clusters,
        "repeated_fault_clusters_60s": len(repeats),
        "possible_output_stalls": possible_stalls,
        "ack_latency_us": {
            "recorded_samples": len(latency),
            "missing_individual_samples": unobserved_latency,
            "median": statistics.median(latency) if latency else None,
            "p95": p95,
            "max_observed": max_latency,
            "max_reported_cumulative": last_worst,
            "over_50ms": sum(x > 50_000 for x in latency),
            "over_100ms": sum(x > 100_000 for x in latency),
        },
        "warnings": warnings,
        "scope": "Last 128 retained snapshots only; no proof of hardware playback, silence, or audible onset.",
    }


def format_text(name: str, report: dict) -> str:
    inc = report["observed_counter_increments"]
    lat = report["ack_latency_us"]
    duration = report["observed_elapsed_ms"]
    lines = [
        f"SWITCH AUDIO CSV ANALYSIS — {name}",
        f"Assessment: {report['assessment']} (telemetry only; not an audio listening test)",
        f"Retained rows: {report['rows']}  Duration in retained window: "
        + (f"{duration / 1000:.1f}s" if duration is not None else "unknown (clock rollback)"),
        f"Status: {report['starting_status']} -> {report['ending_status']}; "
        f"ERROR status entries: {report['error_status_entries']}",
        f"Observed HOME resumes: +{inc['home_resumes']}; PCM pages: +{inc['output_pages']}",
        f"Observed device faults: PCM +{inc['pcm_fail']}, HOME +{inc['home_fail']}, "
        f"lease +{inc['lease_fail']}",
        f"Recoveries: PCM +{inc['pcm_recover']}, HOME +{inc['home_recover']}; "
        f"restart attempts +{inc['pcm_restart'] + inc['home_reopen']}",
        f"Fault clusters (<=60s): {len(report['fault_clusters_60s'])}, "
        f"repeated: {report['repeated_fault_clusters_60s']}",
        f"Possible output stalls: {len(report['possible_output_stalls'])}",
        f"Historical gaps: {report['historical_gaps']}; evicted incident "
        f"counts: {report['unlocalized_faults']}",
        f"Confirmed PCM acknowledgement latency: {lat['recorded_samples']} samples; "
        f"median {lat['median']} us; p95 {lat['p95']} us; "
        f"max {lat['max_observed']} us",
        f"Counter rollbacks: {report['counter_rollbacks'] or 'none'}",
    ]
    lines.extend("NOTE: " + w for w in report["warnings"])
    lines.append("Only retained snapshots were analyzed; no original game assets or physical playback were verified.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_file", type=Path, nargs="+",
                        help="CSV file(s) copied from Switch SD card")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="print a human-readable or machine-readable report")
    args = parser.parse_args(argv)
    reports = []
    for path in args.csv_file:
        try:
            reports.append({"file": str(path), **summarize(load_csv(path))})
        except LogFormatError as exc:
            print(f"{path}: {exc}", file=sys.stderr)
            return 2
    if args.format == "json":
        print(json.dumps(reports, indent=2, ensure_ascii=False))
    else:
        print("\n\n".join(format_text(r["file"], r) for r in reports))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
