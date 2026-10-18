#!/usr/bin/env python3
"""Stage305: locate terminal exact-zero PCM onset relative to host Plus snapshots.

Recorded host file sizes are buffered observations, not guest event timestamps,
audible playback evidence, or proof that Plus caused any audio transition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    FRAME_BYTES, RATE, VirtualPcmEvidenceError, analyze_pair,
    read_report, require_file,
)
from analyze_nexium_pcm_scene_silence import classify_silence
from audit_nexium_pcm_marker_uncertainty import audit_envelopes, source_runs
from audit_nexium_pcm_terminal_silence import classify_recording_edges
from audit_nexium_pcm_recorder_stop import audit_recorder_stop
from audit_nexium_pcm_exit_controls import audit_controls

SCHEMA = "vh-nexium-host-plus-buffered-pcm-onset-fence/v1"


def count_exact_zeros(runs: list[tuple[int, int]],
                      first: int, last: int) -> dict:
    if type(first) is not int or type(last) is not int or not 0 <= first <= last:
        raise VirtualPcmEvidenceError("invalid PCM source window")
    zero = sum(max(0, min(end, last) - max(start, first))
               for start, end in runs)
    touched = sum(start < last and first < end for start, end in runs)
    frames = last - first
    if zero > frames:
        raise VirtualPcmEvidenceError("overlapping original zero runs")
    return {
        "start_frame": first,
        "end_frame_exclusive": last,
        "frames": frames,
        "exact_zero_stereo_frames": zero,
        "nonzero_stereo_frames": frames - zero,
        "original_zero_runs_intersecting": touched,
    }


def audit_plus_fence(raw: bytes, s300: dict, s301: dict, s302: dict,
                     s303: dict, s304: dict, stop_csv: bytes,
                     control_csv: bytes, *, rate: int = RATE) -> dict:
    if type(rate) is not int or rate < 10:
        raise VirtualPcmEvidenceError("invalid PCM sample rate")
    actual = audit_controls(raw, s300, s301, s302, s303,
                            stop_csv, control_csv, rate=rate)
    if s304 != actual:
        raise VirtualPcmEvidenceError("Stage304 source evidence not reproducible")
    controls = s304["exit_control_snapshots"]
    press, release, control_end = controls
    frame_count = len(raw) // FRAME_BYTES
    if (len(raw) != frame_count * FRAME_BYTES or
            frame_count != s302["total_pcm_frames"] or
            s304["scene_pcm_sha256"] != hashlib.sha256(raw).hexdigest()):
        raise VirtualPcmEvidenceError("Stage305 source PCM not frame aligned")
    if (press["potentially_touched_frames"] >
            release["fully_observed_frames"]):
        raise VirtualPcmEvidenceError("host input events span reversed PCM frames")

    runs = source_runs(raw)
    if sum(b - a for a, b in runs) != s302["original_exact_zero_frames"]:
        raise VirtualPcmEvidenceError("source exact-zero frame sum changed")
    if len(runs) != s302["original_exact_zero_runs"]:
        raise VirtualPcmEvidenceError("original exact-zero run count changed")

    # The diagnostic bracket is the unambiguously *fully written* frames
    # between two host file-size snapshots. A partially written stereo
    # frame is never assigned a false sample-accurate event timestamp.
    bracket = count_exact_zeros(
        runs, press["potentially_touched_frames"],
        release["fully_observed_frames"])
    lookback = min(frame_count, rate // 2)  # 500 ms, frame-quantized
    baseline = count_exact_zeros(
        runs, max(0, press["fully_observed_frames"] - lookback),
        press["fully_observed_frames"])
    after_release = count_exact_zeros(
        runs, release["potentially_touched_frames"],
        min(frame_count, release["potentially_touched_frames"] + lookback))
    tail = s302["terminal_run"]
    if tail is None:
        onset = None
    else:
        start = tail["start_frame"]
        if start <= press["fully_observed_frames"]:
            position = "present_by_before_plus_snapshot"
        elif (start > press["potentially_touched_frames"] and
              start <= release["fully_observed_frames"]):
            position = "between_buffered_plus_snapshots"
        elif start > release["potentially_touched_frames"]:
            position = "later_than_after_plus_snapshot"
        else:
            position = "ambiguous_partial_stereo_frame_boundary"

        # Bound source-frame distance from BOTH snapshots; positive =
        # zero run starts after the corresponding byte-size snapshot.
        onset = {
            "start_frame": start,
            "end_frame_exclusive": tail["end_frame_exclusive"],
            "frames": tail["frames"],
            "position_relative_to_buffered_snapshots": position,
            "frames_after_press_snapshot_min":
                start - press["potentially_touched_frames"],
            "frames_after_press_snapshot_max":
                start - press["fully_observed_frames"],
            "frames_before_release_snapshot_min":
                release["fully_observed_frames"] - start,
            "frames_before_release_snapshot_max":
                release["potentially_touched_frames"] - start,
            "seconds_from_press_snapshot_if_naively_sample_aligned":
                round((start - press["fully_observed_frames"]) / rate, 6),
            "sample_alignment_is_not_host_input_timestamp": True,
        }
        if tail["end_frame_exclusive"] != frame_count:
            raise VirtualPcmEvidenceError("terminal zero run no longer at EOF")
        if position == "between_buffered_plus_snapshots" and not (
                onset["frames_after_press_snapshot_min"] > 0 and
                onset["frames_before_release_snapshot_min"] >= 0):
            raise VirtualPcmEvidenceError("positive bracket classification invalid")

    delta_frames = (release["fully_observed_frames"] -
                    press["fully_observed_frames"])
    delta_host_ms = (release["host_epoch_ms"] -
                     press["host_epoch_ms"])
    return {
        "schema": SCHEMA,
        "result": "SOURCE_BOUND_PLUS_BUFFERED_ZERO_RUN_ONSET_FENCED",
        "original_scene_pcm_sha256": hashlib.sha256(raw).hexdigest(),
        "original_scene_pcm_frames": frame_count,
        "sample_rate_hz": rate,
        "plus_hold_host_ms_between_snapshots": delta_host_ms,
        "pcm_frames_written_between_aligned_snapshot_floors": delta_frames,
        "naive_frame_count_minus_expected_from_host_ms":
            round(delta_frames - rate * delta_host_ms / 1000, 3),
        "plus_snapshot_control_window": bracket,
        "before_plus_500ms_baseline": baseline,
        "after_plus_500ms_window": after_release,
        "control_sequence_end_host_pcm_frame":
            control_end["fully_observed_frames"],
        "terminal_exact_zero_onset": onset,
        "all_original_stage299_through_stage304_evidence_replayed": True,
        "file_size_and_wall_time_snapshots_are_not_guest_input_timestamps": True,
        "temporal_overlap_is_not_plus_audio_causality": True,
        "original_soundtrack_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("monitor", "monitor-report", "scenes", "scene-report",
                 "events", "stage299", "stage300", "stage301", "stage302",
                 "stage303", "stage304", "stop-csv", "control-csv", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite Stage305 report")
        original299 = read_report(a.stage299)
        if original299 != analyze_pair(
                a.monitor, a.monitor_report, a.scenes, a.scene_report, a.events):
            raise VirtualPcmEvidenceError("Stage299 source mismatch")
        raw = require_file(a.scenes, "original NeXium scene PCM")
        original300 = read_report(a.stage300)
        if original300 != classify_silence(
                raw, original299, read_report(a.scene_report)):
            raise VirtualPcmEvidenceError("Stage300 source mismatch")
        original301 = read_report(a.stage301)
        if original301 != audit_envelopes(raw, original300):
            raise VirtualPcmEvidenceError("Stage301 source mismatch")
        original302 = read_report(a.stage302)
        if original302 != classify_recording_edges(
                raw, original300, original301):
            raise VirtualPcmEvidenceError("Stage302 source mismatch")
        stop = require_file(a.stop_csv, "actual recorder stop lifecycle")
        original303 = read_report(a.stage303)
        if original303 != audit_recorder_stop(
                raw, original300, original301, original302, stop):
            raise VirtualPcmEvidenceError("Stage303 source mismatch")
        original304 = read_report(a.stage304)
        controls = require_file(a.control_csv, "host Plus controls")
        result = audit_plus_fence(
            raw, original300, original301, original302, original303,
            original304, stop, controls)
        a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "terminal_onset": result["terminal_exact_zero_onset"],
            "before_plus_500ms": result["before_plus_500ms_baseline"],
            "after_plus_500ms": result["after_plus_500ms_window"],
            "hardware_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"result": "STAGE305_PCM_PLUS_FENCE_NOT_VERIFIED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
