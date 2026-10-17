#!/usr/bin/env python3
"""Explore scene-correlated stereo PCM change from A/B events in NeXium.

Event markers are host PCM file-length snapshots and have recording buffer jitter;
no sample-exact guest event timing, original music, or audible speakers are proved.
"""
from __future__ import annotations
import argparse
from array import array
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

RATE = 48000
FRAME_BYTES = 4
EXPECTED = ("field_initial", "focus_1", "field_1", "focus_2", "field_2")
STABILIZE_S = 1.5
END_MARGIN_S = 0.5
MIN_ACTIVE_S = 2.0

class SceneEvidenceError(ValueError):
    pass

def scene_features(pcm: array, first_frame: int, end_frame: int) -> dict:
    n = end_frame - first_frame
    if n <= 0:
        raise SceneEvidenceError("empty stable scene window")
    rms = []
    zcr = []
    for channel in (0, 1):
        energy = crossings = 0
        prev = None
        for i in range(first_frame * 2 + channel, end_frame * 2, 2):
            value = pcm[i]
            energy += value * value
            if prev is not None and ((value < 0) != (prev < 0)):
                crossings += 1
            prev = value
        rms.append(round(math.sqrt(energy / n), 3))
        zcr.append(round(crossings / (2 * n / RATE), 3))
    return {
        "duration_seconds": round(n / RATE, 3),
        "rms_by_channel": rms,
        "zero_crossings_hz_by_channel": zcr,
        "non_silent_rms": min(rms) >= 30.0,
    }

def analyze(audio_path: Path, marker_path: Path) -> dict:
    if audio_path.is_symlink() or not audio_path.is_file():
        raise SceneEvidenceError("audio must be a regular file")
    if marker_path.is_symlink() or not marker_path.is_file():
        raise SceneEvidenceError("markers must be a regular file")
    data = audio_path.read_bytes()
    if len(data) < RATE * FRAME_BYTES * 30 or len(data) % FRAME_BYTES:
        raise SceneEvidenceError("audio too short or not stereo s16le")
    with marker_path.open(encoding="ascii", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 5 or [row.get("scene") for row in rows] != list(EXPECTED):
        raise SceneEvidenceError("expected exactly field/focus/field/focus/field marker sequence")
    if any(set(row) != {"scene", "pcm_bytes", "epoch_ms"} for row in rows):
        raise SceneEvidenceError("event schema mismatch")
    try:
        offsets = [int(row["pcm_bytes"]) for row in rows]
        epochs = [int(row["epoch_ms"]) for row in rows]
    except (TypeError, ValueError) as exc:
        raise SceneEvidenceError("invalid marker offset or timestamp") from exc
    if (any(offset < 0 or offset % FRAME_BYTES for offset in offsets)
        or offsets != sorted(set(offsets))
        or offsets[-1] >= len(data)
        or epochs != sorted(set(epochs))):
        raise SceneEvidenceError("marker offsets or wall times are not strictly increasing/aligned")
    samples = array("h")
    samples.frombytes(data)
    if sys.byteorder != "little":
        samples.byteswap()
    stable_frames = int(STABILIZE_S * RATE)
    margin_frames = int(END_MARGIN_S * RATE)
    intervals = []
    for i, row in enumerate(rows):
        start = offsets[i] // FRAME_BYTES + stable_frames
        end = (offsets[i + 1] // FRAME_BYTES if i + 1 < len(rows)
               else len(data) // FRAME_BYTES) - margin_frames
        if end - start < MIN_ACTIVE_S * RATE:
            raise SceneEvidenceError("scene interval too short for settled audio")
        interval = {"scene": row["scene"],
                    "event_offset_seconds": round(offsets[i] / (RATE * FRAME_BYTES), 3),
                    "recorded_host_epoch_ms": epochs[i]}
        interval.update(scene_features(samples, start, end))
        intervals.append(interval)
    field_zcr = [sum(i["zero_crossings_hz_by_channel"]) / 2
                 for i in intervals if i["scene"].startswith("field")]
    focus_zcr = [sum(i["zero_crossings_hz_by_channel"]) / 2
                 for i in intervals if i["scene"].startswith("focus")]
    field_median = statistics.median(field_zcr)
    focus_median = statistics.median(focus_zcr)
    ratio = focus_median / field_median if field_median else None
    higher = min(focus_zcr) > max(field_zcr) * 1.15
    lower = max(focus_zcr) < min(field_zcr) * 0.85
    all_non_silent = all(item["non_silent_rms"] for item in intervals)
    return {
        "schema": "vh-nexium-scene-audio/v1",
        "evidence_scope": "host virtual PCM and approximate user-input offset snapshots",
        "hardware_status": "HARDWARE NOT TESTED",
        "pcm_sha256": hashlib.sha256(data).hexdigest(),
        "format": "s16le stereo 48000 Hz",
        "pcm_duration_seconds": round(len(data) / (RATE * FRAME_BYTES), 3),
        "offset_accuracy": "HOST_BUFFERED_APPROXIMATE_NOT_GUEST_TIMESTAMP",
        "intervals": intervals,
        "median_field_zero_crossings_hz": round(field_median, 3),
        "median_focus_zero_crossings_hz": round(focus_median, 3),
        "focus_to_field_zero_crossing_ratio": round(ratio, 4) if ratio is not None else None,
        "consistent_frequency_class_separation": bool(higher or lower),
        "result": ("REPEATED_SCENE_CORRELATED_PCM_CHANGE"
                   if all_non_silent and (higher or lower)
                   else "SCENE_PCM_CHANGE_NOT_ESTABLISHED"),
        "scene_change_proven_causal": False,
        "original_soundtrack_confirmed": False,
        "audible_music_confirmed": False,
    }

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcm", type=Path)
    p.add_argument("events", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args(argv)
    try:
        report = analyze(a.pcm, a.events)
        result = json.dumps(report, indent=2) + "\n"
        if a.output is not None:
            if a.output.exists() or a.output.is_symlink():
                raise SceneEvidenceError("refuse to overwrite existing report")
            a.output.write_text(result, encoding="utf-8")
        else:
            print(result, end="")
    except (SceneEvidenceError, OSError, UnicodeError) as e:
        print(json.dumps({"result": "INVALID_SCENE_EVIDENCE", "error": str(e)}), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
