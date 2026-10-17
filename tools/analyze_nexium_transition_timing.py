#!/usr/bin/env python3
"""Estimate scene detection relative to buffered host PCM markers, not guest latency.

A scene change cannot establish original music, hardware timing, absence of
underruns, or audible playback. Low-RMS windows may be intentional rests.
"""
from __future__ import annotations
import argparse
from array import array
import csv
import json
import math
from pathlib import Path
import sys

import analyze_nexium_scene_audio as scene

RATE = 48000
WINDOW_MS = 300
HOP_MS = 100
CONSECUTIVE = 3
SEARCH_MS = 1600
DROP_WINDOW_MS = 10
DROP_RANGE_BEFORE_MS = 500
DROP_RANGE_AFTER_MS = 1500
LOW_RMS = 32.0


def load_samples(path: Path) -> array:
    data = path.read_bytes()
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def features(samples: array, first: int, count: int) -> tuple[float, float]:
    """Average two-channel sign-transition rate and combined window RMS."""
    if first < 0 or first + count > len(samples) // 2 or count <= 1:
        raise scene.SceneEvidenceError("PCM window out of bounds")
    crosses = total = 0
    left = right = 0
    for i in range(first, first + count):
        l, r = samples[2 * i], samples[2 * i + 1]
        total += l * l + r * r
        if i > first:
            crosses += (l < 0) != (left < 0)
            crosses += (r < 0) != (right < 0)
        left, right = l, r
    return crosses * RATE / (4 * count), math.sqrt(total / (count * 2))


def drop_stats(samples: array, marker_frame: int) -> dict:
    block = max(1, RATE * DROP_WINDOW_MS // 1000)
    first = max(0, marker_frame - RATE * DROP_RANGE_BEFORE_MS // 1000)
    last = min(len(samples) // 2, marker_frame + RATE * DROP_RANGE_AFTER_MS // 1000)
    low = longest = run = clips = 0
    for start in range(first, last - block + 1, block):
        _, rms = features(samples, start, block)
        if rms < LOW_RMS:
            low += 1
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        for value in samples[2 * start:2 * (start + block)]:
            clips += abs(value) >= 32767
    return {
        "low_rms_10ms_windows": low,
        "longest_contiguous_low_rms_ms": longest * DROP_WINDOW_MS,
        "observed_full_scale_clipped_sample_values": clips,
        "low_rms_not_equivalent_to_underrun": True,
    }


def analyze(pcm_path: Path, event_path: Path) -> dict:
    baseline = scene.analyze(pcm_path, event_path)
    with event_path.open(encoding="ascii", newline="") as stream:
        markers = list(csv.DictReader(stream))
    samples = load_samples(pcm_path)
    field_rates, focus_rates = [], []
    for state in baseline["intervals"]:
        mean = sum(state["zero_crossings_hz_by_channel"]) / 2
        (focus_rates if state["scene"].startswith("focus") else field_rates).append(mean)
    if min(focus_rates) > max(field_rates) * 1.15:
        direction = 1
        threshold = (min(focus_rates) + max(field_rates)) / 2
    elif min(field_rates) > max(focus_rates) * 1.15:
        direction = -1
        threshold = (min(field_rates) + max(focus_rates)) / 2
    else:
        direction = 0
        threshold = None

    window = max(2, RATE * WINDOW_MS // 1000)
    hop = max(1, RATE * HOP_MS // 1000)
    transitions = []
    for row in markers[1:]:
        event_frame = int(row["pcm_bytes"]) // 4
        expected_focus = row["scene"].startswith("focus")
        bins = []
        for step in range(SEARCH_MS // HOP_MS + 1):
            first = event_frame + step * hop
            if first + window > len(samples) // 2:
                break
            zcr, rms = features(samples, first, window)
            predicted_focus = direction * zcr > direction * threshold if direction else False
            good = direction != 0 and rms >= 80 and predicted_focus == expected_focus
            bins.append((good, zcr, rms))
        first_confirmed = None
        for k in range(len(bins) - CONSECUTIVE + 1):
            if all(item[0] for item in bins[k:k + CONSECUTIVE]):
                first_confirmed = k * HOP_MS
                break
        result = {
            "scene": row["scene"],
            "marker_pcm_offset_seconds": round(event_frame / RATE, 3),
            "stable_expected_scene_detected": first_confirmed is not None,
            "first_confirmed_window_start_ms_after_marker": first_confirmed,
            "end_of_three_window_confirmation_ms_after_marker": (
                first_confirmed + WINDOW_MS + (CONSECUTIVE - 1) * HOP_MS
                if first_confirmed is not None else None),
            "marker_may_lag_guest_input": True,
            "audio_underruns_not_proven_or_excluded": True,
        }
        result.update(drop_stats(samples, event_frame))
        transitions.append(result)
    return {
        "schema": "vh-nexium-scene-transition-observations/v1",
        "pcm_sha256": baseline["pcm_sha256"],
        "hardware_status": "HARDWARE NOT TESTED",
        "scene_evidence": baseline["result"],
        "host_marker_precision": "BUFFERED_FILE_POSITION_NOT_GUEST_INPUT_TIME",
        "timing_result": "HOST_RELATIVE_DETECTION_ONLY"
                         if direction else "INSUFFICIENT_SCENE_SEPARATION",
        "search_after_marker_ms": SEARCH_MS,
        "window_ms": WINDOW_MS,
        "hop_ms": HOP_MS,
        "required_consecutive_windows": CONSECUTIVE,
        "classification_zcr_threshold_hz": round(threshold, 3)
                                           if threshold is not None else None,
        "music_pitch_accuracy_proven": False,
        "actual_input_to_audio_latency_ms": None,
        "physical_switch_tested": False,
        "transitions": transitions,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcm", type=Path)
    parser.add_argument("events", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze(args.pcm, args.events)
        payload = json.dumps(report, indent=2) + "\n"
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise scene.SceneEvidenceError("refuse to overwrite report")
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
    except (scene.SceneEvidenceError, OSError, UnicodeError) as exc:
        print(json.dumps({"result": "INVALID_TRANSITION_EVIDENCE",
                          "error": str(exc)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
