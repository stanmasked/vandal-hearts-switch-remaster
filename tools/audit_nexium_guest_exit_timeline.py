#!/usr/bin/env python3
"""Stage307: optional source-bound guest internal exit milestones from NeXium SD.

Only an observed, canonical guest CSV is evidence. Missing guest SD mirror
is NOT OBSERVED, never a synthetic completion or a proof of audio behavior.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

EVENTS = (
    "plus_observed",
    "stop_requested",
    "worker_cleanup_entered",
    "audout_closed",
    "worker_joined",
)
SCHEMA = "vh-nexium-guest-exit-software-timeline/v1"
UNOBSERVED = "NOT_OBSERVED_GUEST_SD_TRANSPORT"
OBSERVED = "GUEST_EXIT_SOFTWARE_MILESTONES_ORDERED"
SUBDIR = Path("sdmc/switch/vandal-hearts-remake")


class ExitTimelineError(ValueError):
    pass


def parse_exit_csv(raw: bytes) -> dict:
    if not raw or b"\r" in raw or not raw.endswith(b"\n") or b"\x00" in raw:
        raise ExitTimelineError("guest exit receipt not canonical LF CSV")
    try:
        text = raw.decode("ascii")
        r = csv.DictReader(text.splitlines(), strict=True)
        if r.fieldnames != ["event", "guest_monotonic_ns"]:
            raise ExitTimelineError("guest exit schema mismatch")
        rows = list(r)
    except (UnicodeError, csv.Error) as e:
        raise ExitTimelineError("invalid guest exit CSV") from e
    if len(rows) != len(EVENTS) or tuple(x.get("event") for x in rows) != EVENTS:
        raise ExitTimelineError("missing or reordered guest exit milestones")
    times = []
    for row in rows:
        if set(row) != {"event", "guest_monotonic_ns"}:
            raise ExitTimelineError("unexpected guest exit field")
        v = row["guest_monotonic_ns"]
        if not v or not v.isascii() or not v.isdecimal() or (
                len(v) > 1 and v.startswith("0")):
            raise ExitTimelineError("noncanonical guest monotonic integer")
        stamp = int(v)
        if stamp > (1 << 64) - 1:
            raise ExitTimelineError("timestamp overflow")
        times.append(stamp)

    missing = [EVENTS[i] for i, t in enumerate(times) if t == 0]
    observed_times = [t for t in times if t != 0]
    # Even an INCOMPLETE witness must not conceal reversed/tied observed
    # guest milestones behind one missing value.
    if any(a >= b for a, b in zip(observed_times, observed_times[1:])):
        raise ExitTimelineError("observed guest exit events reversed or tied")
    orderly = not missing
    return {
        "schema": SCHEMA,
        "result": OBSERVED if orderly else "GUEST_EXIT_EVENTS_INCOMPLETE",
        "guest_exit_csv_sha256": hashlib.sha256(raw).hexdigest(),
        "guest_monotonic_timestamps_ns": dict(zip(EVENTS, times)),
        "missing_guest_milestones": missing,
        "plus_observed_to_stop_requested_ns":
            times[1] - times[0] if orderly else None,
        "stop_request_to_worker_cleanup_ns":
            times[2] - times[1] if orderly else None,
        "worker_cleanup_to_audout_close_ns":
            times[3] - times[2] if orderly else None,
        "audout_close_to_worker_join_ns":
            times[4] - times[3] if orderly else None,
        "guest_monotonic_clock_is_not_host_keydown_or_DAC_clock": True,
        "host_PCM_to_guest_timestamp_mapping_verified": False,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def audit_guest_root(root: Path) -> dict:
    if (root.is_symlink() or not root.is_dir()):
        raise ExitTimelineError("unsafe NeXium guest SD root")
    sd = root / SUBDIR
    if sd.is_symlink():
        raise ExitTimelineError("unsafe NeXium guest SD subdirectory")
    candidates = sorted(sd.glob("audio-exit-timeline-*.csv")) if sd.is_dir() else []
    if not candidates:
        return {
            "schema": SCHEMA,
            "result": UNOBSERVED,
            "guest_csv_path": None,
            "guest_sd_receipt_observed": False,
            "host_PCM_to_guest_timestamp_mapping_verified": False,
            "original_soundtrack_or_audible_dropout_verified": False,
            "physical_Nintendo_Switch_audio_tested": False,
        }
    if len(candidates) != 1 or candidates[0].name != "audio-exit-timeline-000.csv":
        raise ExitTimelineError("ambiguous or misplaced guest exit receipt")
    p = candidates[0]
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 1024:
        raise ExitTimelineError("invalid guest exit receipt file")
    report = parse_exit_csv(p.read_bytes())
    report["guest_csv_path"] = str(p.relative_to(root))
    report["guest_sd_receipt_observed"] = True
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--guest-root-file", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise ExitTimelineError("refuse overwrite guest exit audit")
        source = args.guest_root_file
        if source.is_symlink() or not source.is_file():
            raise ExitTimelineError("missing authentic NeXium root locator")
        path = source.read_text(encoding="utf-8").strip()
        if not path.startswith("/") or "\n" in path or "\x00" in path:
            raise ExitTimelineError("nonabsolute or invalid guest root")
        report = audit_guest_root(Path(path))
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({"result": report["result"],
                          "guest_sd_receipt_observed":
                              report["guest_sd_receipt_observed"],
                          "physical_audio_tested": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, UnicodeError):
        print(json.dumps({"result": "STAGE307_GUEST_EXIT_RECEIPT_INVALID"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
