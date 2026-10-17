#!/usr/bin/env python3
"""Strict stage-269 guest SD audout telemetry audit; no audio-output claims."""
import argparse
import csv
import json
from pathlib import Path

HEADER = [
    "scope", "second", "attempts", "returns", "failures", "max_call_us",
    "queue_ok", "queue_errors", "queue_min", "queue_max",
    "overwritten_windows", "clock_errors",
]
NUMERIC = HEADER[1:]

def read_telemetry(path: Path) -> dict:
    with path.open("r", encoding="ascii", newline="") as f:
        rows = list(csv.reader(f, strict=True))
    if not rows or rows[0] != HEADER or len(rows) < 3:
        raise ValueError("invalid audout telemetry header/row count")
    if any(len(row) != len(HEADER) or any(not cell for cell in row)
           for row in rows[1:]):
        raise ValueError("missing fields or unexpected columns")
    parsed = []
    for row in rows[1:]:
        item = {"scope": row[0]}
        for key, cell in zip(NUMERIC, row[1:]):
            if key == "second" and row[0] == "TOTAL" and cell == "-1":
                item[key] = -1
            elif not cell.isascii() or not cell.isdecimal():
                raise ValueError("invalid numeric field " + key)
            else:
                item[key] = int(cell)
        parsed.append(item)
    total, *windows = parsed
    if total["scope"] != "TOTAL" or total["second"] != -1:
        raise ValueError("first row must be TOTAL")
    if any(w["scope"] != "SECOND" for w in windows):
        raise ValueError("unexpected window type or duplicate TOTAL")
    if total["overwritten_windows"] or total["clock_errors"]:
        raise ValueError("capture incomplete: evicted windows/clock reversal")
    if any(w["overwritten_windows"] or w["clock_errors"] for w in windows):
        raise ValueError("invalid per-second metadata")
    seconds = [w["second"] for w in windows]
    if seconds != list(range(len(windows))):
        raise ValueError("missing, duplicated or disordered second")
    if len(windows) < 50:
        raise ValueError("not a sustained full-session run")
    for row in parsed:
        if row["returns"] + row["failures"] != row["attempts"]:
            raise ValueError("audout release/error accounting mismatch")
        if row["queue_ok"] == 0 and (row["queue_min"] or row["queue_max"]):
            raise ValueError("unmeasured queue count cannot be nonzero")
        if row["queue_ok"] and row["queue_min"] > row["queue_max"]:
            raise ValueError("reversed queue sample extrema")
    for key in ["attempts", "returns", "failures", "queue_ok", "queue_errors"]:
        if sum(w[key] for w in windows) != total[key]:
            raise ValueError("window totals mismatch: " + key)
    if total["attempts"] < 100:
        raise ValueError("insufficient audout attempts for 50-second test")
    expected_probes = (total["attempts"] + 15) // 16
    if total["queue_ok"] + total["queue_errors"] != expected_probes:
        raise ValueError("expected 1/16 pre-submit service queries")
    if max(w["max_call_us"] for w in windows) != total["max_call_us"]:
        raise ValueError("maximum call-duration summary mismatch")
    return {
        "result": "GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT",
        "scope": "guest-internal pre-submit queue probes and buffer returns",
        "windows": len(windows),
        "attempts": total["attempts"],
        "releases": total["returns"],
        "failed_attempts": total["failures"],
        "max_call_us": total["max_call_us"],
        "queue_probes_ok": total["queue_ok"],
        "queue_probes_failed": total["queue_errors"],
        "queue_min_pre_submit": total["queue_min"] if total["queue_ok"] else None,
        "queue_max_pre_submit": total["queue_max"] if total["queue_ok"] else None,
        "overwritten_windows": 0,
        "clock_errors": 0,
        "underruns_measured": False,
        "hardware_tested": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = read_telemetry(args.source)
    if args.output.exists():
        raise FileExistsError("refuse overwrite of telemetry audit")
    args.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
