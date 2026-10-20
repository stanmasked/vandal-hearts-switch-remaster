#!/usr/bin/env python3
"""Stage304: source-bound buffered PCM snapshots around the real Plus exit action.

These host snapshots measure recorded file length, not guest sample-accurate
input time, music callbacks, audio correctness or physical console sound.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    FRAME_BYTES, RATE, VirtualPcmEvidenceError,
    analyze_pair, read_report, require_file,
)
from analyze_nexium_pcm_scene_silence import classify_silence
from audit_nexium_pcm_marker_uncertainty import audit_envelopes
from audit_nexium_pcm_terminal_silence import classify_recording_edges
from audit_nexium_pcm_recorder_stop import audit_recorder_stop

SCHEMA = "vh-nexium-exit-control-buffered-pcm-snapshot-v1"
EVENT_NAMES = ("before_plus_down", "after_plus_up", "control_sequence_end")
HEADER = ["event", "pcm_bytes", "host_epoch_ms"]


def control_events(raw_csv: bytes) -> list[dict]:
    if not raw_csv or b"\r" in raw_csv or not raw_csv.endswith(b"\n"):
        raise VirtualPcmEvidenceError("noncanonical exit-control events")
    try:
        plain = raw_csv.decode("ascii")
        reader = csv.DictReader(plain.splitlines(), strict=True)
        if reader.fieldnames != HEADER:
            raise VirtualPcmEvidenceError("unexpected exit-control header")
        lines = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise VirtualPcmEvidenceError("invalid exit-control event CSV") from exc
    if len(lines) != len(EVENT_NAMES):
        raise VirtualPcmEvidenceError("incomplete exit-control event sequence")
    events = []
    for line, name in zip(lines, EVENT_NAMES):
        if line.get("event") != name or set(line) != set(HEADER):
            raise VirtualPcmEvidenceError("wrong exit-control event order")
        parsed = {"event": name}
        for key in ("pcm_bytes", "host_epoch_ms"):
            value = line.get(key)
            if (not isinstance(value, str) or not value.isascii()
                    or not value.isdecimal() or
                    (len(value) > 1 and value.startswith("0"))):
                raise VirtualPcmEvidenceError("noncanonical exit-control number")
            parsed[key] = int(value)
        if parsed["host_epoch_ms"] <= 0:
            raise VirtualPcmEvidenceError("invalid exit-control host epoch")
        events.append(parsed)
    if any(a["pcm_bytes"] > b["pcm_bytes"] or
           a["host_epoch_ms"] >= b["host_epoch_ms"]
           for a, b in zip(events, events[1:])):
        raise VirtualPcmEvidenceError("nonmonotone exit-control snapshots")
    return events


def audit_controls(raw: bytes, stage300: dict, stage301: dict,
                   stage302: dict, stage303: dict,
                   stop_csv: bytes, control_csv: bytes,
                   *, rate: int = RATE) -> dict:
    if type(rate) is not int or rate < 10:
        raise VirtualPcmEvidenceError("invalid source PCM rate")
    if stage303 != audit_recorder_stop(
            raw, stage300, stage301, stage302, stop_csv, rate=rate):
        raise VirtualPcmEvidenceError("Stage303 recorder witness not reproduced")
    events = control_events(control_csv)
    stop = stage303["stop_events"][0]
    scene_marker = stage300["approximate_scene_markers"][-1]
    last_host_epoch = scene_marker["host_epoch_ms"]
    last_host_bytes = scene_marker["pcm_byte_offset"]
    if (events[0]["host_epoch_ms"] <= last_host_epoch or
            events[-1]["host_epoch_ms"] > stop["host_epoch_ms"] or
            events[0]["pcm_bytes"] < last_host_bytes or
            events[-1]["pcm_bytes"] > stop["pcm_bytes"] or
            stop["pcm_bytes"] > len(raw)):
        raise VirtualPcmEvidenceError(
            "control, final scene marker and recorder stop not source-ordered")

    trailing = stage302["terminal_run"]
    snapshot_rows = []
    for ev in events:
        observed_bytes = ev["pcm_bytes"]
        floor_frame = min(len(raw) // FRAME_BYTES, observed_bytes // FRAME_BYTES)
        ceil_frame = min(len(raw) // FRAME_BYTES,
                         (observed_bytes + FRAME_BYTES - 1) // FRAME_BYTES)
        item = {
            "event": ev["event"],
            "pcm_bytes": observed_bytes,
            "host_epoch_ms": ev["host_epoch_ms"],
            "partial_stereo_frame_snapshot": bool(observed_bytes % FRAME_BYTES),
            "fully_observed_frames": floor_frame,
            "potentially_touched_frames": ceil_frame,
        }
        if trailing is not None:
            first, end = trailing["start_frame"], trailing["end_frame_exclusive"]
            lower = max(0, min(end, floor_frame) - first)
            upper = max(0, min(end, ceil_frame) - first)
            if not 0 <= lower <= upper <= end - first:
                raise VirtualPcmEvidenceError("impossible terminal zero overlap")
            item.update({
                "terminal_zero_frames_observed_by_snapshot_min": lower,
                "terminal_zero_frames_observed_by_snapshot_max": upper,
                "terminal_zero_frames_not_yet_observed_min": end - first - upper,
                "terminal_zero_frames_not_yet_observed_max": end - first - lower,
            })
        snapshot_rows.append(item)

    if trailing is not None:
        mins = [x["terminal_zero_frames_observed_by_snapshot_min"]
                for x in snapshot_rows]
        maxs = [x["terminal_zero_frames_observed_by_snapshot_max"]
                for x in snapshot_rows]
        if any(a > b for a, b in zip(mins, mins[1:])) or any(
                a > b for a, b in zip(maxs, maxs[1:])):
            raise VirtualPcmEvidenceError("terminal zero overlaps not monotone")

    return {
        "schema": SCHEMA,
        "result": "SOURCE_BOUND_BUFFERED_EXIT_CONTROL_TIMELINE_RECONCILED",
        "scene_pcm_sha256": hashlib.sha256(raw).hexdigest(),
        "original_scene_pcm_frames": stage302["total_pcm_frames"],
        "last_host_scene_marker": scene_marker,
        "exit_control_snapshots": snapshot_rows,
        "first_plus_control_vs_scene_marker_host_ms":
            events[0]["host_epoch_ms"] - last_host_epoch,
        "last_control_vs_recorder_stop_host_ms":
            stop["host_epoch_ms"] - events[-1]["host_epoch_ms"],
        "original_terminal_zero_run": trailing,
        "all_original_source_witnesses_replayed": True,
        "host_pcm_file_size_snapshots_not_sample_exact": True,
        "plus_input_to_guest_music_stop_causality_proven": False,
        "audio_dropout_or_original_soundtrack_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("monitor", "monitor-report", "scenes", "scene-report",
                 "events", "stage299", "stage300", "stage301", "stage302",
                 "stage303", "stop-csv", "control-csv", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite Stage304 evidence")
        witness299 = read_report(a.stage299)
        if witness299 != analyze_pair(
                a.monitor, a.monitor_report, a.scenes, a.scene_report, a.events):
            raise VirtualPcmEvidenceError("Stage299 source mismatch")
        raw = require_file(a.scenes, "original virtual scene PCM")
        witness300 = read_report(a.stage300)
        if witness300 != classify_silence(
                raw, witness299, read_report(a.scene_report)):
            raise VirtualPcmEvidenceError("Stage300 source mismatch")
        witness301 = read_report(a.stage301)
        if witness301 != audit_envelopes(raw, witness300):
            raise VirtualPcmEvidenceError("Stage301 source mismatch")
        witness302 = read_report(a.stage302)
        if witness302 != classify_recording_edges(
                raw, witness300, witness301):
            raise VirtualPcmEvidenceError("Stage302 source mismatch")
        witness303 = read_report(a.stage303)
        result = audit_controls(
            raw, witness300, witness301, witness302, witness303,
            require_file(a.stop_csv, "host recorder stop events"),
            require_file(a.control_csv, "real host Plus control events"))
        a.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "exit_control_snapshots": result["exit_control_snapshots"],
            "physical_Switch_audio_verified": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Preserve all Stage304 source/provenance guards. An intermittent
        # original host-recorder snapshot mismatch must be diagnosable
        # without inventing a successful virtual audio measurement.
        print(json.dumps({
            "result": "STAGE304_EXIT_PCM_TIMELINE_NOT_VERIFIED",
            "error_kind": type(exc).__name__,
            "source_invariant_failure": str(exc)[:240],
            "physical_Nintendo_Switch_audio_tested": False,
            "guest_speaker_playback_verified": False,
        }, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
