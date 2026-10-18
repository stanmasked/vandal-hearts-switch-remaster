#!/usr/bin/env python3
"""Stage306: compare independently source-audited NeXium Plus/PCM captures.

The *upstream Stage305 auditor* validates the full original PCM/marker
evidence from each recording separately. This comparator deliberately
does not infer a physical audible dropout, guest timestamp or causality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from analyze_nexium_pcm_stream_integrity import VirtualPcmEvidenceError

SCHEMA = "vh-nexium-independent-capture-plus-zero-onset-repeatability/v1"
STAGE305_RESULT = "SOURCE_BOUND_PLUS_BUFFERED_ZERO_RUN_ONSET_FENCED"
CATEGORIES = {
    "present_by_before_plus_snapshot",
    "between_buffered_plus_snapshots",
    "later_than_after_plus_snapshot",
    "ambiguous_partial_stereo_frame_boundary",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def validate_capture(run_id: int, report: dict) -> dict:
    if (type(run_id) is not int or run_id <= 0 or
            not isinstance(report, dict) or
            report.get("result") != STAGE305_RESULT or
            report.get("sample_rate_hz") != 48000 or
            report.get("all_original_stage299_through_stage304_evidence_replayed")
            is not True or
            report.get("file_size_and_wall_time_snapshots_are_not_guest_input_timestamps")
            is not True or
            report.get("temporal_overlap_is_not_plus_audio_causality") is not True or
            report.get("original_soundtrack_or_audible_dropout_verified") is not False or
            report.get("physical_Nintendo_Switch_audio_tested") is not False):
        raise VirtualPcmEvidenceError("invalid Stage305 provenance/scope receipt")
    digest = report.get("original_scene_pcm_sha256")
    frames = report.get("original_scene_pcm_frames")
    if (not isinstance(digest, str) or not SHA256.fullmatch(digest) or
            type(frames) is not int or frames <= 0):
        raise VirtualPcmEvidenceError("invalid captured source identity")
    windows = {}
    for key in ("plus_snapshot_control_window", "before_plus_500ms_baseline",
                "after_plus_500ms_window"):
        window = report.get(key)
        if not isinstance(window, dict):
            raise VirtualPcmEvidenceError("missing original PCM interval")
        a = window.get("start_frame")
        b = window.get("end_frame_exclusive")
        count = window.get("frames")
        zeros = window.get("exact_zero_stereo_frames")
        nonzeros = window.get("nonzero_stereo_frames")
        if (any(type(x) is not int for x in (a, b, count, zeros, nonzeros)) or
                not 0 <= a <= b <= frames or
                b - a != count or zeros + nonzeros != count or
                zeros < 0 or nonzeros < 0):
            raise VirtualPcmEvidenceError("source window frame conservation failed")
        windows[key] = {
            "start_frame": a,
            "end_frame_exclusive": b,
            "frames": count,
            "exact_zero_frames": zeros,
            "nonzero_frames": nonzeros,
        }
    hold = report.get("plus_hold_host_ms_between_snapshots")
    if type(hold) is not int or hold <= 0:
        raise VirtualPcmEvidenceError("bad Plus hold time")
    onset = report.get("terminal_exact_zero_onset")
    if onset is None:
        classification = "no_terminal_zero_run"
        start = None
        press_range = None
        release_range = None
    else:
        if not isinstance(onset, dict):
            raise VirtualPcmEvidenceError("malformed terminal zero-run onset")
        classification = onset.get("position_relative_to_buffered_snapshots")
        start = onset.get("start_frame")
        end = onset.get("end_frame_exclusive")
        length = onset.get("frames")
        press_min = onset.get("frames_after_press_snapshot_min")
        press_max = onset.get("frames_after_press_snapshot_max")
        release_min = onset.get("frames_before_release_snapshot_min")
        release_max = onset.get("frames_before_release_snapshot_max")
        if (classification not in CATEGORIES or
                any(type(x) is not int for x in
                    (start, end, length, press_min, press_max,
                     release_min, release_max)) or
                not 0 <= start < end == frames or
                end - start != length or
                press_min > press_max or release_min > release_max or
                onset.get("sample_alignment_is_not_host_input_timestamp") is not True):
            raise VirtualPcmEvidenceError("terminal original zero run malformed")
        press_range = [press_min, press_max]
        release_range = [release_min, release_max]
        if classification == "between_buffered_plus_snapshots" and not (
                press_min > 0 and release_min >= 0):
            raise VirtualPcmEvidenceError("invalid bracketed onset")
    return {
        "workflow_run_id": run_id,
        "scene_pcm_sha256": digest,
        "scene_pcm_frames": frames,
        "plus_hold_host_ms": hold,
        "terminal_zero_onset_class": classification,
        "terminal_zero_start_frame": start,
        "source_frames_from_press_snapshot_min_max": press_range,
        "source_frames_before_release_snapshot_min_max": release_range,
        "source_windows": windows,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def compare_captures(captures: list[tuple[int, dict]]) -> dict:
    if not isinstance(captures, list) or not 2 <= len(captures) <= 8:
        raise VirtualPcmEvidenceError("require two to eight independent captures")
    rows = [validate_capture(run_id, report) for run_id, report in captures]
    ids = [item["workflow_run_id"] for item in rows]
    digests = [item["scene_pcm_sha256"] for item in rows]
    if len(ids) != len(set(ids)) or len(digests) != len(set(digests)):
        raise VirtualPcmEvidenceError(
            "duplicate GitHub run identifier or identical PCM capture")
    groups = {}
    for row in rows:
        category = row["terminal_zero_onset_class"]
        groups[category] = groups.get(category, 0) + 1
    inside = groups.get("between_buffered_plus_snapshots", 0)
    return {
        "schema": SCHEMA,
        "result": "INDEPENDENT_SOURCE_BOUND_PLUS_PCM_RUNS_COMPARED",
        "run_count": len(rows),
        "runs": rows,
        "distinct_workflow_run_ids": True,
        "distinct_original_scene_pcm_sha256": True,
        "onset_class_counts": groups,
        "same_terminal_onset_class_across_runs": len(groups) == 1,
        "all_terminating_zero_onsets_bracketed_by_host_Plus_snapshots":
            inside == len(rows),
        "host_buffered_snapshots_not_guest_exact_timing": True,
        "sample_frame_proximity_does_not_prove_Plus_causality": True,
        "original_music_or_audible_dropout_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="append", required=True,
                        metavar="GITHUB_RUN_ID:STAGE305_JSON")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite Stage306 output")
        captures = []
        for entry in args.capture:
            run, sep, path = entry.partition(":")
            if not sep or not run.isdecimal() or not path:
                raise VirtualPcmEvidenceError("invalid capture run-id:path pair")
            p = Path(path)
            if p.is_symlink() or not p.is_file():
                raise VirtualPcmEvidenceError("capture JSON not regular file")
            captures.append((int(run), json.loads(p.read_text(encoding="utf-8"))))
        out = compare_captures(captures)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "result": out["result"],
            "onset_class_counts": out["onset_class_counts"],
            "run_count": out["run_count"],
            "causality_proven": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print(json.dumps({"result": "STAGE306_INDEPENDENCE_NOT_VERIFIED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
