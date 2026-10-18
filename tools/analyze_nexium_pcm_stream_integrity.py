#!/usr/bin/env python3
"""Stage299: source-bound PCM stream integrity and discontinuity candidates.

This audits two real PulseAudio virtual-sink recordings of the current
NeXium NRO, NOT DAC output on a physical Nintendo Switch. Raw PCM
cannot prove whether the monitor dropped frames: there is no independent
per-frame production timestamp or expected waveform. A large sample step,
low-RMS region or exact zero run is only a descriptive candidate.
"""
from __future__ import annotations

import argparse
from array import array
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

RATE = 48000
CHANNELS = 2
FRAME_BYTES = 4
BLOCK_FRAMES = 480   # 10 ms
STEP_THRESHOLD = 4096
LOW_RMS_THRESHOLD = 32.0
SCHEMA = "vh-nexium-virtual-pcm-continuity-indicators/v1"
SCENES = ("field_initial", "focus_1", "field_1", "focus_2", "field_2")


class VirtualPcmEvidenceError(ValueError):
    pass


def require_file(path: Path, kind: str) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise VirtualPcmEvidenceError(f"{kind} must be an existing regular file")
    return path.read_bytes()


def read_report(path: Path) -> dict:
    raw = require_file(path, "pinned report")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise VirtualPcmEvidenceError("malformed pinned JSON report") from exc
    if not isinstance(obj, dict):
        raise VirtualPcmEvidenceError("report must be a JSON object")
    return obj


def scene_markers(path: Path, raw_length: int) -> list[dict]:
    raw = require_file(path, "scene event markers")
    if b"\r" in raw or not raw.endswith(b"\n"):
        raise VirtualPcmEvidenceError("noncanonical scene event CSV")
    try:
        content = raw.decode("ascii")
        reader = csv.DictReader(content.splitlines())
        if reader.fieldnames != ["scene", "pcm_bytes", "epoch_ms"]:
            raise VirtualPcmEvidenceError("unexpected scene event marker schema")
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise VirtualPcmEvidenceError("invalid scene event CSV") from exc
    if len(rows) != len(SCENES) or tuple(x["scene"] for x in rows) != SCENES:
        raise VirtualPcmEvidenceError("unexpected scene sequence")
    offsets, epochs = [], []
    for row in rows:
        if set(row) != {"scene", "pcm_bytes", "epoch_ms"}:
            raise VirtualPcmEvidenceError("unexpected scene marker columns")
        for k in ("pcm_bytes", "epoch_ms"):
            v = row[k]
            if not v or not v.isascii() or not v.isdecimal() or (
                len(v) > 1 and v.startswith("0")
            ):
                raise VirtualPcmEvidenceError("noncanonical integer scene marker")
        offset = int(row["pcm_bytes"])
        epoch = int(row["epoch_ms"])
        if offset % FRAME_BYTES or not 0 <= offset < raw_length or epoch <= 0:
            raise VirtualPcmEvidenceError("unaligned or out-of-bounds scene marker")
        offsets.append(offset)
        epochs.append(epoch)
    if any(b <= a for a, b in zip(offsets, offsets[1:])) or any(
        b <= a for a, b in zip(epochs, epochs[1:])
    ):
        raise VirtualPcmEvidenceError("scene marker sequence not strictly increasing")
    return [{"scene": row["scene"], "pcm_byte_offset": off,
             "host_epoch_ms": when, "approximate_frame_offset": off // FRAME_BYTES}
            for row, off, when in zip(rows, offsets, epochs)]


def scan_pcm(path: Path, pinned: dict, *, kind: str,
             marker_path: Path | None = None) -> dict:
    if kind not in ("monitor", "scenes"):
        raise VirtualPcmEvidenceError("unknown independent guest PCM capture")
    raw = require_file(path, kind + " virtual PCM")
    if len(raw) < FRAME_BYTES or len(raw) % FRAME_BYTES:
        raise VirtualPcmEvidenceError("raw virtual PCM has incomplete stereo s16le frames")
    digest = hashlib.sha256(raw).hexdigest()
    if (pinned.get("pcm_sha256") != digest or
            pinned.get("format") != "s16le stereo 48000 Hz" or
            pinned.get("hardware_status") != "HARDWARE NOT TESTED"):
        raise VirtualPcmEvidenceError("raw PCM is not identical to pinned capture report")
    frames = len(raw) // FRAME_BYTES
    if kind == "monitor":
        if (pinned.get("schema") != "vh-nexium-pcm-quality/v1" or
                pinned.get("bytes") != len(raw) or
                pinned.get("frames") != frames or
                pinned.get("duration_seconds") != round(frames / RATE, 3) or
                pinned.get("audible_music_confirmed") is not False or
                pinned.get("original_soundtrack_confirmed") is not False):
            raise VirtualPcmEvidenceError("monitor PCM metadata fails existing audit")
        if marker_path is not None:
            raise VirtualPcmEvidenceError("monitor capture cannot use scene markers")
        markers = None
    else:
        if (pinned.get("schema") != "vh-nexium-scene-audio/v1" or
                pinned.get("pcm_duration_seconds") != round(frames / RATE, 3)
                or pinned.get("offset_accuracy") !=
                   "HOST_BUFFERED_APPROXIMATE_NOT_GUEST_TIMESTAMP"
                or pinned.get("scene_change_proven_causal") is not False
                or pinned.get("audible_music_confirmed") is not False):
            raise VirtualPcmEvidenceError("scene PCM metadata fails existing audit")
        if marker_path is None:
            raise VirtualPcmEvidenceError("scene PCM requires its actual host event CSV")
        markers = scene_markers(marker_path, len(raw))

    samples = array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()

    step_count = boundary_steps = max_step = 0
    exact_zero_frames = longest_zero = zero_run = zero_run_count = 0
    zero_runs_at_least_10ms = 0
    block_hashes = hashlib.sha256()
    block_count = 0
    exact_zero_blocks = 0
    low_rms_blocks = 0
    longest_low_blocks = low_streak = 0
    preceding_left = preceding_right = None
    for first in range(0, frames, BLOCK_FRAMES):
        last = min(frames, first + BLOCK_FRAMES)
        block = raw[first * FRAME_BYTES:last * FRAME_BYTES]
        block_hashes.update(hashlib.sha256(block).digest())
        block_count += 1
        block_energy = 0
        block_all_zero = True
        for frame in range(first, last):
            left = samples[frame * CHANNELS]
            right = samples[frame * CHANNELS + 1]
            block_energy += left * left + right * right
            if left != 0 or right != 0:
                block_all_zero = False
            else:
                exact_zero_frames += 1
            if left == 0 and right == 0:
                zero_run += 1
                longest_zero = max(longest_zero, zero_run)
            elif zero_run:
                zero_run_count += 1
                zero_runs_at_least_10ms += zero_run >= BLOCK_FRAMES
                zero_run = 0
            if preceding_left is not None:
                delta = max(abs(left - preceding_left),
                            abs(right - preceding_right))
                max_step = max(max_step, delta)
                if delta >= STEP_THRESHOLD:
                    step_count += 1
                    boundary_steps += frame % BLOCK_FRAMES == 0
            preceding_left, preceding_right = left, right
        if block_all_zero:
            exact_zero_blocks += 1
        block_rms = math.sqrt(block_energy / (2 * (last - first)))
        if block_rms < LOW_RMS_THRESHOLD:
            low_rms_blocks += 1
            low_streak += 1
            longest_low_blocks = max(longest_low_blocks, low_streak)
        else:
            low_streak = 0
    if zero_run:
        zero_run_count += 1
        zero_runs_at_least_10ms += zero_run >= BLOCK_FRAMES
    if block_count != (frames + BLOCK_FRAMES - 1) // BLOCK_FRAMES:
        raise VirtualPcmEvidenceError("PCM segment accounting dropped source frames")

    return {
        "kind": kind,
        "pcm_sha256": digest,
        "pcm_bytes": len(raw),
        "frames": frames,
        "duration_seconds": round(frames / RATE, 3),
        "format": "s16le stereo 48000 Hz",
        "pinned_prior_report_reconciled": True,
        "analysis_block_frames": BLOCK_FRAMES,
        "analysis_blocks": block_count,
        "final_partial_block_frames": frames % BLOCK_FRAMES,
        "sha256_of_concatenated_10ms_block_digests":
            block_hashes.hexdigest(),
        "exact_zero_stereo_frames": exact_zero_frames,
        "exact_zero_stereo_runs": zero_run_count,
        "longest_exact_zero_stereo_run_frames": longest_zero,
        "longest_exact_zero_stereo_run_seconds":
            round(longest_zero / RATE, 6),
        "exact_zero_10ms_blocks": exact_zero_blocks,
        "zero_runs_at_least_10ms": zero_runs_at_least_10ms,
        "low_rms_10ms_blocks": low_rms_blocks,
        "longest_low_rms_10ms_streak": longest_low_blocks,
        "max_abs_adjacent_sample_delta": max_step,
        "adjacent_frame_deltas_ge4096": step_count,
        "ge4096_deltas_at_10ms_block_boundaries": boundary_steps,
        "scene_event_markers": markers,
        "possible_sample_discontinuities_are_not_verified_dropouts": True,
        "host_buffered_scene_event_timestamps_not_sample_exact": True,
        "missing_frames_cannot_be_proven_from_pcm_bytes_alone": True,
        "guest_audio_queue_state_not_measured_by_pcm": True,
        "physical_console_DAC_or_audible_glitches_measured": False,
    }


def analyze_pair(monitor: Path, monitor_report: Path, scenes: Path,
                 scene_report: Path, events: Path) -> dict:
    left = scan_pcm(monitor, read_report(monitor_report), kind="monitor")
    right = scan_pcm(scenes, read_report(scene_report), kind="scenes",
                     marker_path=events)
    if left["pcm_sha256"] == right["pcm_sha256"]:
        raise VirtualPcmEvidenceError("two independent capture streams have identical bytes")
    return {
        "schema": SCHEMA,
        "result": "TWO_ORIGINAL_NEXIUM_VIRTUAL_PCM_STREAMS_AUDITED",
        "monitor_capture": left,
        "scene_capture": right,
        "distinct_current_run_virtual_PCM_sources": True,
        "both_prior_PCM_audits_bound_by_exact_SHA256": True,
        "all_stereo_frames_and_10ms_blocks_accounted": True,
        "host_recording_bytes_do_not_supply_per_frame_capture_timestamps": True,
        "dropped_or_duplicated_audio_frames_proven": False,
        "no_guest_sample_exact_reference_waveform_available": True,
        "soundtrack_identity_or_audible_playback_verified": False,
        "physical_Nintendo_Switch_hardware_tested": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--monitor", type=Path, required=True)
    p.add_argument("--monitor-report", type=Path, required=True)
    p.add_argument("--scenes", type=Path, required=True)
    p.add_argument("--scene-report", type=Path, required=True)
    p.add_argument("--events", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        if a.output.exists() or a.output.is_symlink():
            raise VirtualPcmEvidenceError("refuse overwrite of prior PCM source witness")
        report = analyze_pair(a.monitor, a.monitor_report, a.scenes,
                              a.scene_report, a.events)
        a.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
        print(json.dumps({
            "result": report["result"],
            "monitor": {
                "frames": report["monitor_capture"]["frames"],
                "zero_runs_10ms": report["monitor_capture"]["zero_runs_at_least_10ms"],
                "large_adjacent_steps": report["monitor_capture"]["adjacent_frame_deltas_ge4096"],
            },
            "scenes": {
                "frames": report["scene_capture"]["frames"],
                "zero_runs_10ms": report["scene_capture"]["zero_runs_at_least_10ms"],
                "large_adjacent_steps": report["scene_capture"]["adjacent_frame_deltas_ge4096"],
            },
            "hardware_tested": False,
        }, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"result": "VIRTUAL_PCM_STREAM_INTEGRITY_NOT_VERIFIED",
                          "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
