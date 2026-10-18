#!/usr/bin/env python3
"""Stage311: independently re-audit archived ORIGINAL guest exit CSV source.

Stage310 binds guest SD original bytes to the NeXium runtime artifact.
Stage311 replays the artifact on a DIFFERENT workflow runner. It does not
trust earlier JSON summaries: regenerates Stage307, Stage308 and Stage310
witnesses from the exact archived guest-created CSV and optical PNG.
No host PCM sample-clock or physical audio claim is inferred.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from audit_nexium_guest_exit_timeline import (
    OBSERVED, SCHEMA as STAGE307_SCHEMA,
    ExitTimelineError, parse_exit_csv, SUBDIR,
)
from audit_nexium_guest_optical_exit_clock import (
    BOTH, audit_guest_clocks,
)
from audit_switch_guest_scene_trace import TraceError

SCHEMA = "vh-nexium-independent-original-guest-exit-archive-replay/v1"
ORIGINAL = "audio-exit-timeline-000.csv"
PNG = "scene-optical-trace.png"
REPORTS = (
    "guest-audio-exit-timeline-stage307.json",
    "guest-optical-exit-clock-stage308.json",
    "guest-original-exit-source-stage310.json",
)


def reconstructed_stage310(original: bytes, optical: dict) -> dict:
    digest = hashlib.sha256(original).hexdigest()
    return {
        "schema": "vh-nexium-original-guest-exit-csv-preservation/v1",
        "result": "ORIGINAL_GUEST_EXIT_CSV_BYTES_PRESERVED_AND_REAUDITED",
        "original_guest_exit_csv_preserved": True,
        "original_guest_exit_csv_filename": ORIGINAL,
        "original_guest_exit_csv_size": len(original),
        "guest_exit_receipt_sha256": digest,
        "optical_scene_png_sha256": optical["optical_scene_png_sha256"],
        "guest_exit_software_chronology_verified": True,
        "original_source_csv_bytes_independently_reaudited": True,
        "guest_to_host_pcm_clock_mapping_verified": False,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def independent_archive_replay(original: bytes, optical_png: bytes,
                               stage307: dict, stage308: dict,
                               stage310: dict, run_id: int) -> dict:
    if type(run_id) is not int or run_id <= 0:
        raise TraceError("missing immutable original workflow run identifier")
    if not isinstance(stage307, dict) or not isinstance(stage308, dict) or not isinstance(stage310, dict):
        raise TraceError("archived report missing")
    if not original or len(original) > 1024 or len(optical_png) > 10_000_000:
        raise TraceError("invalid original guest exit file or optical PNG size")
    try:
        guest = parse_exit_csv(original)
    except (ExitTimelineError, UnicodeError) as exc:
        raise TraceError("original archived guest exit CSV invalid") from exc
    if guest["result"] != OBSERVED or guest.get("schema") != STAGE307_SCHEMA:
        raise TraceError("archived guest exit source not fully observed")
    # The ORIGINAL guest file path, not an attacker-specified JSON path.
    guest["guest_csv_path"] = str(SUBDIR / ORIGINAL)
    guest["guest_sd_receipt_observed"] = True
    if guest != stage307:
        raise TraceError("Stage307 archived receipt does not reproduce from raw CSV")
    optical = audit_guest_clocks(optical_png, guest)
    if optical.get("result") != BOTH or optical.get("guest_exit_order_verified") is not True:
        raise TraceError("original guest optical scene/exit order not verified")
    if optical != stage308:
        raise TraceError("Stage308 archived optical receipt not reproducible")
    expected_stage310 = reconstructed_stage310(original, optical)
    if expected_stage310 != stage310:
        raise TraceError("Stage310 preserved original source receipt mismatch")
    stamps = guest["guest_monotonic_timestamps_ns"]
    fields = ("plus_observed", "stop_requested",
              "worker_cleanup_entered", "audout_closed", "worker_joined")
    intervals = {
        "plus_to_stop_requested_ns":
            stamps[fields[1]] - stamps[fields[0]],
        "stop_request_to_worker_cleanup_ns":
            stamps[fields[2]] - stamps[fields[1]],
        "worker_cleanup_to_audout_close_ns":
            stamps[fields[3]] - stamps[fields[2]],
        "audout_close_to_worker_join_ns":
            stamps[fields[4]] - stamps[fields[3]],
        "plus_observed_to_worker_joined_ns":
            stamps[fields[4]] - stamps[fields[0]],
    }
    if any(type(v) is not int or v <= 0 for v in intervals.values()):
        raise TraceError("nonpositive source guest software interval")
    return {
        "schema": SCHEMA,
        "result": "INDEPENDENT_ORIGINAL_GUEST_EXIT_BYTES_FULLY_REPLAYED",
        "original_capture_workflow_run_id": run_id,
        "original_guest_csv_sha256": hashlib.sha256(original).hexdigest(),
        "original_guest_csv_bytes": len(original),
        "original_guest_csv_bytes_independently_reaudited": True,
        "original_optical_png_sha256": hashlib.sha256(optical_png).hexdigest(),
        "original_optical_packet_sha256": optical["optical_packet_sha256"],
        "source_stage307_receipt_reproduced": True,
        "source_stage308_receipt_reproduced": True,
        "source_stage310_receipt_reproduced": True,
        "guest_software_exit_intervals_ns": intervals,
        "guest_scene_last_event_to_observed_plus_ns":
            optical["scene_last_event_to_plus_ns"],
        "retail_audio_assets_present_in_receipt": False,
        "guest_software_clock_not_calibrated_to_host_pcm": True,
        "audible_music_or_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def read_archive(root: Path) -> tuple:
    if root.is_symlink() or not root.is_dir():
        raise TraceError("unsafe or missing original NeXium evidence archive")
    expected = (ORIGINAL, PNG, *REPORTS)
    candidates = {}
    for filename in expected:
        matches = list(root.rglob(filename))
        if len(matches) != 1:
            raise TraceError(f"original archive has missing/ambiguous {filename}")
        p = matches[0]
        if p.is_symlink() or not p.is_file():
            raise TraceError("archived original evidence is symlink/non-file")
        candidates[filename] = p
    common = candidates[ORIGINAL].parent
    if any(p.parent != common for p in candidates.values()):
        raise TraceError("archive source and JSON files not co-located")
    node = common
    while node != root:
        if node.is_symlink() or node == node.parent:
            raise TraceError("untrusted archived evidence directory")
        node = node.parent
    raw = candidates[ORIGINAL].read_bytes()
    optical = candidates[PNG].read_bytes()
    reports = []
    for p in REPORTS:
        if candidates[p].stat().st_size > 16384:
            raise TraceError("unbounded archived evidence receipt")
        reports.append(json.loads(candidates[p].read_text(encoding="utf-8")))
    return raw, optical, *reports


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-run-id", type=int, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise TraceError("never replace independent Stage311 receipt")
        raw, png, s307, s308, s310 = read_archive(args.archive)
        result = independent_archive_replay(
            raw, png, s307, s308, s310, args.original_run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "original_workflow_run_id": result["original_capture_workflow_run_id"],
            "source_sha256": result["original_guest_csv_sha256"],
            "independent_original_bytes": True,
            "hardware_sound_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        print(json.dumps({"result": "STAGE311_ORIGINAL_SOURCE_REPLAY_NOT_VERIFIED",
                          "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
