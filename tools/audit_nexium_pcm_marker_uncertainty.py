#!/usr/bin/env python3
"""Stage301: sensitivity of source-recorded PCM zeros to approximate host markers.

The 250/500/1000 ms envelopes are hypothetical, not measured timestamp error.
Nothing here identifies guest callbacks, queue underflow, or audible glitches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from analyze_nexium_pcm_stream_integrity import (
    RATE, FRAME_BYTES, VirtualPcmEvidenceError,
    analyze_pair, read_report, require_file,
)
from analyze_nexium_pcm_scene_silence import (
    SCHEMA as STAGE300_SCHEMA, classify_silence, zone_partition,
)

SCHEMA = "vh-nexium-pcm-host-marker-envelope-sensitivity/v1"
RADII_MS = (250, 500, 1000)
ZERO_FRAME = b"\x00\x00\x00\x00"


def source_runs(raw: bytes) -> list[tuple[int, int]]:
    """Re-scan original stereo s16le frames without Stage300's run scanner."""
    if not raw or len(raw) % FRAME_BYTES:
        raise VirtualPcmEvidenceError("Stage301 requires complete stereo PCM frames")
    runs = []
    start = None
    for pos in range(0, len(raw), FRAME_BYTES):
        frame = pos // FRAME_BYTES
        zero = raw[pos:pos + FRAME_BYTES] == ZERO_FRAME
        if zero and start is None:
            start = frame
        elif not zero and start is not None:
            runs.append((start, frame))
            start = None
    if start is not None:
        runs.append((start, len(raw) // FRAME_BYTES))
    return runs


def intersection(runs: list[tuple[int, int]], a: int, b: int) -> tuple[int, int]:
    """Return zero-frame intersection and number of source runs touched."""
    frames = 0
    touched = 0
    for first, last in runs:
        overlap = max(0, min(last, b) - max(first, a))
        if overlap:
            frames += overlap
            touched += 1
    return frames, touched


def audit_envelopes(raw: bytes, stage300: dict, *, rate: int = RATE) -> dict:
    if type(rate) is not int or rate < 10 or not isinstance(stage300, dict):
        raise VirtualPcmEvidenceError("invalid Stage301 audit input")
    frames = len(raw) // FRAME_BYTES
    runs = source_runs(raw)
    markers = stage300.get("approximate_scene_markers")
    if (stage300.get("schema") != STAGE300_SCHEMA or
            stage300.get("result") !=
            "SOURCE_BOUND_SCENE_SILENCE_BY_APPROXIMATE_HOST_MARKERS_RECONCILED" or
            stage300.get("scene_pcm_sha256") != hashlib.sha256(raw).hexdigest() or
            stage300.get("scene_pcm_frames") != frames or
            stage300.get("marker_count") != 5 or
            stage300.get("zero_runs_are_not_verified_audio_dropouts") is not True or
            stage300.get("scene_input_or_music_transition_causality_proven") is not False or
            stage300.get("actual_guest_scheduler_or_DAC_state_measured") is not False or
            stage300.get("original_soundtrack_or_physical_speaker_output_verified") is not False):
        raise VirtualPcmEvidenceError("unverified Stage300 PCM source or scope")
    zones = zone_partition(markers, frames, rate=rate)
    observed = stage300.get("zones")
    minimum = stage300.get("long_run_minimum_frames")
    if (not isinstance(observed, list) or len(observed) != len(zones) or
            type(minimum) is not int or minimum != max(1, rate // 10)):
        raise VirtualPcmEvidenceError("Stage300 zone/long-run definition mismatch")

    zeros = sum(end - start for start, end in runs)
    longs = [(a, b) for a, b in runs if b - a >= minimum]
    long_frames = sum(b - a for a, b in longs)
    if (stage300.get("exact_zero_runs_total") != len(runs) or
            stage300.get("exact_zero_frames_total") != zeros or
            stage300.get("exact_zero_longest_run_frames") !=
            max((b - a for a, b in runs), default=0) or
            stage300.get("long_run_count") != len(longs) or
            stage300.get("long_run_frames_total") != long_frames):
        raise VirtualPcmEvidenceError("Stage300 original zero-run inventory changed")

    # Independently check every Stage300 reported partition, not only totals.
    for expected, reported in zip(zones, observed):
        if not isinstance(reported, dict) or any(
                reported.get(k) != v for k, v in expected.items()):
            raise VirtualPcmEvidenceError("Stage300 zone boundary diverges")
        a, b = expected["start_frame"], expected["end_frame_exclusive"]
        actual_zero, _ = intersection(runs, a, b)
        actual_long, actual_long_intersections = intersection(longs, a, b)
        if (reported.get("exact_zero_frames") != actual_zero or
                reported.get("long_run_zero_frames") != actual_long or
                reported.get("long_run_intersections") != actual_long_intersections or
                reported.get("zero_fraction_of_zone") !=
                round(actual_zero / (b - a), 6)):
            raise VirtualPcmEvidenceError("Stage300 zone frame count changed")

    profiles = []
    for radius_ms in RADII_MS:
        radius = radius_ms * rate // 1000
        if radius <= 0:
            raise VirtualPcmEvidenceError("invalid marker sensitivity resolution")
        windows = []
        previous_end = 0
        total_inside = total_long_inside = coverage = 0
        for marker in markers:
            center = marker["approximate_frame_offset"]
            a = max(0, center - radius)
            b = min(frames, center + radius)
            if a < previous_end or b <= a:
                raise VirtualPcmEvidenceError("overlapping/empty marker envelopes")
            previous_end = b
            count, touch = intersection(runs, a, b)
            long_count, _ = intersection(longs, a, b)
            windows.append({
                "scene": marker["scene"],
                "start_frame": a,
                "end_frame_exclusive": b,
                "frames": b - a,
                "exact_zero_frames": count,
                "long_run_zero_frames": long_count,
                "zero_runs_intersecting": touch,
            })
            total_inside += count
            total_long_inside += long_count
            coverage += b - a
        if total_inside > zeros or total_long_inside > long_frames or coverage > frames:
            raise VirtualPcmEvidenceError("impossible envelope conservation")
        # Count unique source runs, even if a long run crosses two envelopes.
        touched_unique = sum(any(a < y and x < b for a, b in
                                 ((w["start_frame"], w["end_frame_exclusive"])
                                  for w in windows))
                             for x, y in runs)
        profiles.append({
            "hypothetical_radius_ms": radius_ms,
            "radius_frames": radius,
            "envelopes": windows,
            "envelope_frames": coverage,
            "outside_envelope_frames": frames - coverage,
            "exact_zero_frames_inside": total_inside,
            "exact_zero_frames_outside": zeros - total_inside,
            "long_run_zero_frames_inside": total_long_inside,
            "long_run_zero_frames_outside": long_frames - total_long_inside,
            "unique_zero_runs_intersecting_envelopes": touched_unique,
        })
    if any(x["exact_zero_frames_inside"] > y["exact_zero_frames_inside"]
           or x["long_run_zero_frames_inside"] > y["long_run_zero_frames_inside"]
           for x, y in zip(profiles, profiles[1:])):
        raise VirtualPcmEvidenceError("nonmonotone envelope sensitivity")
    return {
        "schema": SCHEMA,
        "result": "SOURCE_BOUND_HYPOTHETICAL_MARKER_ENVELOPES_RECONCILED",
        "scene_pcm_sha256": stage300["scene_pcm_sha256"],
        "total_pcm_frames": frames,
        "exact_zero_frames_total": zeros,
        "long_run_zero_frames_total": long_frames,
        "profiles": profiles,
        "all_source_frames_and_zero_runs_accounted": True,
        "marker_offset_error_measured": False,
        "hypothetical_windows_are_not_confidence_intervals": True,
        "audio_dropout_or_scene_causality_proven": False,
        "physical_speaker_output_or_original_soundtrack_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("monitor", "monitor-report", "scenes", "scene-report",
                  "events", "stage299", "stage300", "output"):
        parser.add_argument("--" + label, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists() or args.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite of Stage301 evidence")
        original299 = read_report(args.stage299)
        if original299 != analyze_pair(args.monitor, args.monitor_report,
                                       args.scenes, args.scene_report, args.events):
            raise VirtualPcmEvidenceError("Stage299 not reproducible from source")
        raw = require_file(args.scenes, "source scene PCM")
        original300 = read_report(args.stage300)
        if original300 != classify_silence(raw, original299,
                                           read_report(args.scene_report)):
            raise VirtualPcmEvidenceError("Stage300 not reproducible from source")
        result = audit_envelopes(raw, original300)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({
            "result": result["result"],
            "exact_zero_frames_inside_by_radius":
                {x["hypothetical_radius_ms"]: x["exact_zero_frames_inside"]
                 for x in result["profiles"]},
            "physical_audio_verified": False,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"result": "STAGE301_MARKER_SENSITIVITY_NOT_VERIFIED"}),
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
