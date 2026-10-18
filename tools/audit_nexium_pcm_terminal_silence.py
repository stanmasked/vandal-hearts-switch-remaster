#!/usr/bin/env python3
"""Stage302: separate boundary-censored recorded silence from interior runs.

This is a re-audit of captured virtual PCM, not proof of audible underruns,
guest audio shutdown, playback completion, or physical Switch audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    RATE, VirtualPcmEvidenceError, analyze_pair, read_report, require_file,
)
from analyze_nexium_pcm_scene_silence import classify_silence
from audit_nexium_pcm_marker_uncertainty import (
    SCHEMA as STAGE301_SCHEMA, audit_envelopes, source_runs,
)

SCHEMA = "vh-nexium-pcm-boundary-censored-exact-silence/v1"
KINDS = ("whole_recording", "recording_start", "interior", "recording_end")


def classify_recording_edges(raw: bytes, stage300: dict, stage301: dict,
                             *, rate: int = RATE) -> dict:
    """Account for *all* exact-zero runs, with exclusive censoring classes."""
    if type(rate) is not int or rate < 10 or not isinstance(stage300, dict):
        raise VirtualPcmEvidenceError("invalid Stage302 source")
    # This recomputes the Stage301 sensitivity audit, which also
    # independently checks every reported Stage300 zone against raw PCM.
    if not isinstance(stage301, dict) or stage301 != audit_envelopes(
            raw, stage300, rate=rate):
        raise VirtualPcmEvidenceError("Stage301 report diverges from source PCM")
    if (stage301.get("schema") != STAGE301_SCHEMA or
            stage301.get("marker_offset_error_measured") is not False or
            stage301.get("audio_dropout_or_scene_causality_proven") is not False or
            stage301.get("physical_speaker_output_or_original_soundtrack_verified")
            is not False):
        raise VirtualPcmEvidenceError("Stage301 scope overclaim")

    total = stage301["total_pcm_frames"]
    runs = source_runs(raw)
    limit = stage300["long_run_minimum_frames"]
    markers = stage300["approximate_scene_markers"]
    tail_marker = markers[-1]["approximate_frame_offset"]
    counters = {k: {"run_count": 0, "frames": 0,
                    "long_run_count": 0, "long_run_frames": 0} for k in KINDS}
    rows = []
    long_rows = []
    for start, end in runs:
        if start == 0 and end == total:
            kind = "whole_recording"
        elif start == 0:
            kind = "recording_start"
        elif end == total:
            kind = "recording_end"
        else:
            kind = "interior"
        length = end - start
        long = length >= limit
        rec = counters[kind]
        rec["run_count"] += 1
        rec["frames"] += length
        if long:
            rec["long_run_count"] += 1
            rec["long_run_frames"] += length
        item = {"start_frame": start, "end_frame_exclusive": end,
                "frames": length, "classification": kind,
                "long_run": long}
        rows.append(item)
        if long:
            long_rows.append(item)

    if (sum(x["run_count"] for x in counters.values()) !=
            stage300["exact_zero_runs_total"] or
            sum(x["frames"] for x in counters.values()) !=
            stage300["exact_zero_frames_total"] or
            sum(x["long_run_count"] for x in counters.values()) !=
            stage300["long_run_count"] or
            sum(x["long_run_frames"] for x in counters.values()) !=
            stage300["long_run_frames_total"] or
            len(runs) != stage300["exact_zero_runs_total"] or
            stage301["exact_zero_frames_total"] !=
            stage300["exact_zero_frames_total"] or
            hashlib.sha256(raw).hexdigest() !=
            stage300["scene_pcm_sha256"]):
        raise VirtualPcmEvidenceError("source PCM boundary classification not conserved")

    # Check all top-20 long-run boundaries against the original Stage300
    # receipt, not merely their aggregate counts.
    original_top = stage300.get("longest_zero_runs_top20")
    calculated_top = sorted(long_rows, key=lambda r: (-r["frames"], r["start_frame"]))[:20]
    if not isinstance(original_top, list) or len(original_top) != len(calculated_top):
        raise VirtualPcmEvidenceError("Stage300 longest zero-run index mismatch")
    for observed, expected in zip(original_top, calculated_top):
        if (not isinstance(observed, dict) or
                any(observed.get(k) != expected[k] for k in
                    ("start_frame", "end_frame_exclusive", "frames")) or
                observed.get("seconds") != round(expected["frames"] / rate, 6)):
            raise VirtualPcmEvidenceError("Stage300 top-20 original run changed")

    trailing = rows[-1] if rows and rows[-1]["end_frame_exclusive"] == total else None
    if trailing is not None and trailing["classification"] not in (
            "recording_end", "whole_recording"):
        raise VirtualPcmEvidenceError("trailing original zero run misclassified")
    return {
        "schema": SCHEMA,
        "result": "SOURCE_BOUND_EXACT_ZERO_RUN_RECORDING_CENSORSHIP_RECONCILED",
        "scene_pcm_sha256": stage300["scene_pcm_sha256"],
        "total_pcm_frames": total,
        "original_exact_zero_runs": len(runs),
        "original_exact_zero_frames": stage300["exact_zero_frames_total"],
        "long_run_minimum_frames": limit,
        "counts_by_recording_boundary": counters,
        "terminal_run": trailing,
        "terminal_run_starts_after_last_host_marker":
            (trailing["start_frame"] >= tail_marker if trailing else None),
        "original_long_runs_by_censor_class": long_rows,
        "whole_recording_is_not_double_counted": True,
        "every_original_zero_frame_accounted_once": True,
        "marker_offset_error_measured": False,
        "virtual_monitor_end_cannot_establish_gameplay_or_audio_end": True,
        "absence_of_guest_queue_timestamp_or_expected_soundtrack": True,
        "audible_dropout_or_music_scene_causality_verified": False,
        "physical_Nintendo_Switch_audio_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("monitor", "monitor-report", "scenes", "scene-report",
                 "events", "stage299", "stage300", "stage301", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite of Stage302 report")
        original299 = read_report(a.stage299)
        if original299 != analyze_pair(a.monitor, a.monitor_report,
                                        a.scenes, a.scene_report, a.events):
            raise VirtualPcmEvidenceError("Stage299 not reproducible")
        raw = require_file(a.scenes, "scene PCM")
        original300 = read_report(a.stage300)
        if original300 != classify_silence(
                raw, original299, read_report(a.scene_report)):
            raise VirtualPcmEvidenceError("Stage300 not reproducible")
        result = classify_recording_edges(raw, original300, read_report(a.stage301))
        a.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "counters": result["counts_by_recording_boundary"],
            "trailing_original_zero_run": result["terminal_run"],
            "physical_Switch_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"result": "STAGE302_SOURCE_BOUND_SILENCE_NOT_VERIFIED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
