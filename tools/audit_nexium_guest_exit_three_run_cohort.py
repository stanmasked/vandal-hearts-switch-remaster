#!/usr/bin/env python3
"""Stage312: three independent NeXium guest shutdowns with mixed provenance.

Two historic captures have capture-time audited guest exit JSON only. The
third has the ORIGINAL guest-created CSV independently replayed in Stage311.
Never report source-byte revalidation for the older archived receipts.
Software guest clock is not synchronized to host PCM, audout DAC, speakers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
import sys

from audit_switch_guest_scene_trace import TraceError
from compare_nexium_guest_exit_cohort import compare_sessions, load_capture
from replay_nexium_original_guest_exit_archive import (
    read_archive, independent_archive_replay,
)

SCHEMA = "vh-independent-three-guest-exit-provenance-cohort/v1"
INTERVALS = {
    "plus_to_stop_request_ns": "plus_to_stop_requested_ns",
    "stop_request_to_worker_cleanup_ns": "stop_request_to_worker_cleanup_ns",
    "worker_cleanup_to_audout_close_ns": "worker_cleanup_to_audout_close_ns",
    "audout_close_to_worker_join_ns": "audout_close_to_worker_join_ns",
    "plus_to_join_ns": "plus_observed_to_worker_joined_ns",
}


def audit_three(sessions: list[tuple], raw_source_run: int,
                raw_replay_inputs: tuple, independent_stage311: dict) -> dict:
    if not isinstance(sessions, list) or len(sessions) != 3:
        raise TraceError("require exactly three original guest exit captures")
    if type(raw_source_run) is not int or raw_source_run <= 0:
        raise TraceError("invalid original raw source workflow ID")
    if not isinstance(independent_stage311, dict):
        raise TraceError("missing independently validated Stage311 receipt")
    comparison = compare_sessions(sessions)
    rows = comparison["source_bound_rows"]
    if len(rows) != 3 or sum(
            r["original_guest_csv_bytes_reverified"] is True for r in rows) != 1:
        raise TraceError("require two legacy receipts and one original raw-CSV replay")
    matches = [session for session in sessions if session[0] == raw_source_run]
    if len(matches) != 1 or matches[0][3] is None:
        raise TraceError("original raw source run missing from three recordings")

    source_bytes, source_optical, s307, s308, s310 = raw_replay_inputs
    original_row = matches[0]
    if (original_row[1] != source_optical or original_row[3] != source_bytes
            or original_row[2] != s307 or original_row[4] != s308):
        raise TraceError("independent replay source files mismatch the source cohort")
    fresh = independent_archive_replay(
        source_bytes, source_optical, s307, s308, s310, raw_source_run)
    if fresh != independent_stage311:
        raise TraceError("separate GitHub Actions Stage311 source receipt mismatch")
    raw_entry = next(r for r in rows if r["workflow_run_id"] == raw_source_run)
    if (raw_entry["guest_exit_csv_sha256"] != fresh["original_guest_csv_sha256"]
            or raw_entry["optical_scene_png_sha256"] != fresh["original_optical_png_sha256"]
            or not fresh["original_guest_csv_bytes_independently_reaudited"]):
        raise TraceError("original raw file and optical CRC do not match cohort")

    for row in rows:
        intervals = row["guest_shutdown_durations_ns"]
        if set(intervals) != set(INTERVALS):
            raise TraceError("incomplete guest exit interval source set")
        if row["original_guest_csv_bytes_reverified"] != (
                row["workflow_run_id"] == raw_source_run):
            raise TraceError("guest original-byte provenance tier falsified")
        if row["workflow_run_id"] == raw_source_run:
            if any(intervals[k] != fresh["guest_software_exit_intervals_ns"][v]
                   for k, v in INTERVALS.items()):
                raise TraceError("original guest shutdown durations do not reproduce")

    durations = {}
    for key in INTERVALS:
        vals = [r["guest_shutdown_durations_ns"][key] for r in rows]
        if any(type(x) is not int or x <= 0 for x in vals):
            raise TraceError("invalid guest exit software duration")
        durations[key] = {
            "minimum_ns": min(vals),
            "maximum_ns": max(vals),
            "median_ns": median(vals),
            "observations": [
                {"run_id": row["workflow_run_id"], "guest_software_ns": value}
                for row, value in zip(rows, vals)
            ],
        }
    return {
        "schema": SCHEMA,
        "result": "THREE_ORIGINAL_GUEST_EXIT_RUNS_PROVENANCE_RECONCILED",
        "run_count": 3,
        "run_ids": [r["workflow_run_id"] for r in rows],
        "guest_raw_original_capture_id": raw_source_run,
        "original_csv_byte_verified_runs": [raw_source_run],
        "capture_time_source_audited_JSON_only_runs": [
            r["workflow_run_id"] for r in rows
            if r["workflow_run_id"] != raw_source_run
        ],
        "original_csv_sha256_revalidated": fresh["original_guest_csv_sha256"],
        "original_optical_packet_sha256_revalidated":
            fresh["original_optical_packet_sha256"],
        "independent_stage311_receipt_reproduced": True,
        "all_three_distinct_optical_PNG_and_guest_exit_SHA256": True,
        "guest_software_duration_distribution_ns": durations,
        "original_sources_have_distinct_workflow_runs": True,
        "older_guest_csv_bytes_NOT_reaudited": True,
        "host_pcm_to_guest_software_clock_calibrated": False,
        "audible_audio_dropout_verified": False,
        "original_retail_soundtrack_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True,
                        metavar="RUN_ID:ORIGINAL_ARTIFACT_DIR")
    parser.add_argument("--raw-original-run", type=int, required=True)
    parser.add_argument("--independent-stage311", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("refuse to overwrite Stage312 independent report")
        if args.independent_stage311.is_symlink() or not args.independent_stage311.is_file():
            raise TraceError("missing real Stage311 independent receipt")
        sessions = []
        raw_archive_dir = None
        for spec in args.capture:
            raw_id, sep, path = spec.partition(":")
            if not sep or not raw_id.isdecimal() or not path:
                raise TraceError("invalid source run:archive pair")
            run = int(raw_id)
            directory = Path(path)
            sessions.append(load_capture(run, directory))
            if run == args.raw_original_run:
                if raw_archive_dir is not None:
                    raise TraceError("duplicated original source archive")
                raw_archive_dir = directory
        if raw_archive_dir is None:
            raise TraceError("third original guest-created CSV archive absent")
        raw_inputs = read_archive(raw_archive_dir)
        independent = json.loads(
            args.independent_stage311.read_text(encoding="utf-8"))
        result = audit_three(sessions, args.raw_original_run,
                             raw_inputs, independent)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "three_original_workflow_runs": result["run_ids"],
            "one_independently_byte_reaudited_raw_csv": True,
            "plus_to_join_guest_software_distribution_ns":
                result["guest_software_duration_distribution_ns"]["plus_to_join_ns"],
            "audible_music_verified": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
        print(json.dumps({
            "result": "STAGE312_GUEST_EXIT_PROVENANCE_NOT_VERIFIED",
            "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
