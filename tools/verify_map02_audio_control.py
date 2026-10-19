#!/usr/bin/env python3
"""Fail-closed two-NRO NeXium virtual-audio contrast; never speaker proof."""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import sys
from pathlib import Path

RATE = 48000
CHANNELS = 2
PCM_BYTES_PER_FRAME = CHANNELS * 2
MIN_ACTIVE_VALUES = 9600


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe_pcm(path: Path) -> dict:
    raw = path.read_bytes()
    if not raw or len(raw) % PCM_BYTES_PER_FRAME:
        raise ValueError(f"Missing or misaligned stereo s16le PCM: {path}")
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    count = len(samples)
    count_loud = sum(abs(s) >= 256 for s in samples)
    rms = math.sqrt(sum(float(s) * s for s in samples) / count)
    return {
        "duration_seconds": round(len(raw) / (RATE * PCM_BYTES_PER_FRAME), 3),
        "sample_values": count,
        "sample_values_abs_ge256": count_loud,
        "rms": round(rms, 3),
        "pcm_sha256": sha256(raw),
    }


def evaluate(control_pcm: Path, audio_pcm: Path, control_nro: Path,
             audio_nro: Path, manifest: Path, audio_sinks: Path,
             min_seconds: float = 30.0) -> dict:
    meta = json.loads(manifest.read_text(encoding="utf-8"))
    if meta.get("schema") != "vh-map02-nro-pair/v1":
        raise ValueError("Unknown NRO-pair manifest schema")
    if not isinstance(meta.get("run_id"), int) or meta["run_id"] <= 0:
        raise ValueError("Missing immutable workflow run ID")
    if not isinstance(meta.get("run_attempt"), int) or meta["run_attempt"] <= 0:
        raise ValueError("Missing immutable workflow run attempt")
    if not isinstance(meta.get("git_sha"), str) or len(meta["git_sha"]) != 40:
        raise ValueError("Missing exact workflow checkout SHA")
    control_sha = sha256(control_nro.read_bytes())
    audio_sha = sha256(audio_nro.read_bytes())
    if control_sha == audio_sha:
        raise ValueError("Control and experimental NRO are identical")
    if control_sha != meta.get("control_nro_sha256"):
        raise ValueError("Control NRO does not match same-run manifest")
    if audio_sha != meta.get("audio_nro_sha256"):
        raise ValueError("Experimental NRO does not match same-run manifest")

    control = describe_pcm(control_pcm)
    active = describe_pcm(audio_pcm)
    audio_sink_seen = "nexium" in audio_sinks.read_text(
        encoding="utf-8", errors="replace").lower()
    durations_ok = min(control["duration_seconds"],
                       active["duration_seconds"]) >= min_seconds
    quiet_control = (control["rms"] < 32.0 and
                     control["sample_values_abs_ge256"] < MIN_ACTIVE_VALUES)
    active_audio = (active["rms"] >= 32.0 and
                    active["sample_values_abs_ge256"] >= MIN_ACTIVE_VALUES)
    ratio_ok = active["rms"] >= max(32.0, 5.0 * control["rms"])
    passed = all((durations_ok, quiet_control, active_audio,
                  ratio_ok, audio_sink_seen))
    return {
        "schema": "vh-map02-virtual-pcm-negative-control/v1",
        "run_id": meta["run_id"],
        "run_attempt": meta["run_attempt"],
        "git_sha": meta["git_sha"],
        "control_nro_sha256": control_sha,
        "audio_nro_sha256": audio_sha,
        "control": control,
        "experimental": active,
        "checks": {
            "both_recordings_long_enough": durations_ok,
            "video_only_control_quiet": quiet_control,
            "opt_in_nro_nonzero": active_audio,
            "experimental_rms_at_least_5x_control": ratio_ok,
            "experimental_guest_sink_observed": audio_sink_seen,
            "same_run_manifest_matches_both_nros": True,
        },
        "status": ("CONTROLLED_VIRTUAL_AUDIO_CONTRAST"
                   if passed else "VIRTUAL_AUDIO_CAUSAL_CONTROL_NOT_ESTABLISHED"),
        "sample_aligned_comparison": False,
        "original_music_or_studio_c_causality_proven": False,
        "physical_switch_audio_tested": False,
        "notes": (
            "Null-sink output, not physical speakers. Control and experiment "
            "were captured sequentially and are not sample-aligned; contrast "
            "cannot independently identify original music or reverb tail."
        )
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--control-pcm", type=Path, required=True)
    p.add_argument("--audio-pcm", type=Path, required=True)
    p.add_argument("--control-nro", type=Path, required=True)
    p.add_argument("--audio-nro", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--audio-sinks", type=Path, required=True)
    p.add_argument("--min-seconds", type=float, default=30.0)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    try:
        if args.min_seconds <= 0:
            raise ValueError("Minimum duration must be positive")
        result = evaluate(args.control_pcm, args.audio_pcm,
                          args.control_nro, args.audio_nro,
                          args.manifest, args.audio_sinks, args.min_seconds)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        result = {"schema": "vh-map02-virtual-pcm-negative-control/v1",
                  "status": "CONTROL_AUDIT_FAILED_CLOSED",
                  "error": str(exc),
                  "original_music_or_studio_c_causality_proven": False,
                  "physical_switch_audio_tested": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) +
                           "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "CONTROLLED_VIRTUAL_AUDIO_CONTRAST" else 1


if __name__ == "__main__":
    raise SystemExit(main())
