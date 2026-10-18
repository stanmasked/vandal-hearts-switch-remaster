#!/usr/bin/env python3
"""Stage303: compare exact recorded EOF zeros to host recorder-stop snapshots.

Byte-size snapshots are buffered host observations, NOT sample-exact guest
audio callback times, original soundtrack references, or hardware playback.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    FRAME_BYTES, RATE, VirtualPcmEvidenceError, analyze_pair,
    read_report, require_file,
)
from analyze_nexium_pcm_scene_silence import classify_silence
from audit_nexium_pcm_marker_uncertainty import audit_envelopes
from audit_nexium_pcm_terminal_silence import classify_recording_edges

SCHEMA = "vh-nexium-host-recorder-stop-snapshot-pcm-v1"
CSV_HEADER = "event,pcm_bytes,host_epoch_ms,signal_success"
EVENTS = ("before_sigint", "after_wait")


def read_stop_events(raw: bytes) -> list[dict]:
    """Validate canonical two-row host lifecycle CSV, without trusting paths."""
    if not raw or b"\r" in raw or not raw.endswith(b"\n"):
        raise VirtualPcmEvidenceError("noncanonical recorder-stop CSV")
    try:
        text = raw.decode("ascii")
        reader = csv.DictReader(text.splitlines(), strict=True)
        if reader.fieldnames != CSV_HEADER.split(","):
            raise VirtualPcmEvidenceError("recorder-stop CSV schema changed")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise VirtualPcmEvidenceError("invalid recorder-stop CSV") from exc
    if len(rows) != 2 or tuple(row.get("event") for row in rows) != EVENTS:
        raise VirtualPcmEvidenceError("missing or reordered recorder lifecycle")
    output = []
    for row in rows:
        if set(row) != set(CSV_HEADER.split(",")):
            raise VirtualPcmEvidenceError("unexpected recorder stop column")
        vals = {}
        for name in ("pcm_bytes", "host_epoch_ms", "signal_success"):
            value = row.get(name)
            if (not isinstance(value, str) or not value.isascii()
                    or not value.isdecimal() or
                    (len(value) > 1 and value.startswith("0"))):
                raise VirtualPcmEvidenceError("noncanonical lifecycle integer")
            vals[name] = int(value)
        if vals["host_epoch_ms"] <= 0 or vals["signal_success"] != 1:
            raise VirtualPcmEvidenceError("unverified recorder SIGINT lifecycle")
        output.append({"event": row["event"], **vals})
    if not (output[0]["host_epoch_ms"] <= output[1]["host_epoch_ms"] and
            output[0]["pcm_bytes"] <= output[1]["pcm_bytes"]):
        raise VirtualPcmEvidenceError("recorder byte/time snapshots not monotone")
    return output


def audit_recorder_stop(raw: bytes, stage300: dict, stage301: dict,
                        stage302: dict, stop_csv: bytes,
                        *, rate: int = RATE) -> dict:
    """Use the original PCM source and Stage302 to bound terminal run position."""
    if type(rate) is not int or rate < 10:
        raise VirtualPcmEvidenceError("invalid PCM rate")
    actual302 = classify_recording_edges(raw, stage300, stage301, rate=rate)
    if stage302 != actual302:
        raise VirtualPcmEvidenceError("Stage302 recording-edge witness changed")
    events = read_stop_events(stop_csv)
    pre = events[0]["pcm_bytes"]
    post = events[1]["pcm_bytes"]
    if (post != len(raw) or post != stage302["total_pcm_frames"] * FRAME_BYTES
            or pre < 0 or pre > post or
            hashlib.sha256(raw).hexdigest() != stage302["scene_pcm_sha256"]):
        raise VirtualPcmEvidenceError("host stop snapshot not source-bound")
    frames = stage302["total_pcm_frames"]
    floor_frame = min(frames, pre // FRAME_BYTES)
    ceil_frame = min(frames, (pre + FRAME_BYTES - 1) // FRAME_BYTES)

    # A raw file stat may race a partial frame write. Report BOTH the
    # definite/possible bounds rather than falsely claiming sample alignment.
    trailing = stage302["terminal_run"]
    if trailing:
        first, end = trailing["start_frame"], trailing["end_frame_exclusive"]
        if (not isinstance(first, int) or not isinstance(end, int) or
                first < 0 or end != frames or end <= first):
            raise VirtualPcmEvidenceError("invalid terminal source run")
        possible_post_signal = max(0, end - max(first, floor_frame))
        definite_post_signal = max(0, end - max(first, ceil_frame))
        before_stop_lower = (end - first) - possible_post_signal
        before_stop_upper = (end - first) - definite_post_signal
        if not 0 <= definite_post_signal <= possible_post_signal <= end - first:
            raise VirtualPcmEvidenceError("terminal stop intersection mismatch")
        run_bounds = {
            "start_frame": first,
            "end_frame_exclusive": end,
            "frames": end - first,
            "classification": trailing["classification"],
            "frames_before_signal_snapshot_min": before_stop_lower,
            "frames_before_signal_snapshot_max": before_stop_upper,
            "frames_after_signal_snapshot_min": definite_post_signal,
            "frames_after_signal_snapshot_max": possible_post_signal,
            "was_already_present_before_signal_snapshot":
                before_stop_lower > 0,
        }
        if (before_stop_lower + possible_post_signal != end - first or
                before_stop_upper + definite_post_signal != end - first):
            raise VirtualPcmEvidenceError("missing terminal source frames")
    else:
        run_bounds = None

    return {
        "schema": SCHEMA,
        "result": "SOURCE_BOUND_HOST_RECORDER_STOP_SNAPSHOT_RECONCILED",
        "scene_pcm_sha256": stage302["scene_pcm_sha256"],
        "scene_pcm_frames": frames,
        "stop_events": events,
        "stop_signal_snapshot_partial_stereo_frame": pre % FRAME_BYTES != 0,
        "buffered_bytes_appended_during_stop": post - pre,
        "stop_wall_interval_ms":
            events[1]["host_epoch_ms"] - events[0]["host_epoch_ms"],
        "terminal_exact_zero_run_stop_overlap": run_bounds,
        "stage302_original_zero_run_classes_conserved": True,
        "host_stop_snapshots_not_sample_exact_guest_audio_times": True,
        "host_stop_signal_does_not_prove_guest_playback_end": True,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("monitor", "monitor-report", "scenes", "scene-report",
                 "events", "stage299", "stage300", "stage301", "stage302",
                 "stop-csv", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite Stage303 recorder evidence")
        original299 = read_report(a.stage299)
        if original299 != analyze_pair(a.monitor, a.monitor_report,
                                       a.scenes, a.scene_report, a.events):
            raise VirtualPcmEvidenceError("Stage299 not source reproducible")
        raw = require_file(a.scenes, "original virtual scene PCM")
        original300 = read_report(a.stage300)
        if original300 != classify_silence(
                raw, original299, read_report(a.scene_report)):
            raise VirtualPcmEvidenceError("Stage300 not source reproducible")
        original301 = read_report(a.stage301)
        if original301 != audit_envelopes(raw, original300):
            raise VirtualPcmEvidenceError("Stage301 not source reproducible")
        original302 = read_report(a.stage302)
        report = audit_recorder_stop(
            raw, original300, original301, original302,
            require_file(a.stop_csv, "original stop lifecycle"))
        a.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
        print(json.dumps({
            "result": report["result"],
            "terminal_run": report["terminal_exact_zero_run_stop_overlap"],
            "buffered_bytes_appended_during_stop":
                report["buffered_bytes_appended_during_stop"],
            "physical_Switch_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"result": "STAGE303_RECORDER_STOP_NOT_VERIFIED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
