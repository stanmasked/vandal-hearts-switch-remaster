#!/usr/bin/env python3
"""Analyze 16-bit PCM WAV output without third-party dependencies.

This is a host-side measurement utility. It does not establish that the Switch
speaker/headphone output is audible or bit-accurate to original PlayStation.
"""
import argparse
import json
import math
import struct
import wave
from pathlib import Path


def analyze(path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        frames = wav.getnframes()
        width = wav.getsampwidth()
        comptype = wav.getcomptype()
        if width != 2 or comptype != "NONE":
            raise ValueError("Expected uncompressed signed 16-bit PCM WAV")
        if channels not in (1, 2) or rate <= 0:
            raise ValueError("Expected mono/stereo PCM with valid sample rate")
        data = wav.readframes(frames)
    if not frames:
        raise ValueError("Empty WAV has no measurable signal")
    samples = struct.unpack("<" + "h" * (len(data) // 2), data)
    if len(samples) != frames * channels:
        raise ValueError("Truncated PCM data")
    results = []
    for c in range(channels):
        seq = samples[c::channels]
        mean = math.fsum(seq) / frames
        rms = math.sqrt(math.fsum(float(x) * x for x in seq) / frames)
        peak = max(abs(x) for x in seq)
        clipped = sum(x in (-32768, 32767) for x in seq)
        results.append({
            "channel": c,
            "rms_dbfs": round(20 * math.log10(rms / 32768), 3) if rms else None,
            "peak_dbfs": round(20 * math.log10(peak / 32768), 3) if peak else None,
            "dc_offset": round(mean / 32768, 7),
            "clipped_samples": clipped,
            "clipped_fraction": round(clipped / frames, 8),
            "silent": peak == 0,
        })
    return {
        "file": str(path),
        "sample_rate_hz": rate,
        "channels": channels,
        "frames": frames,
        "duration_seconds": round(frames / rate, 6),
        "per_channel": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path, help="16-bit uncompressed WAV to analyze")
    parser.add_argument("--expected-rate", type=int, default=48000)
    parser.add_argument("--max-clipped-fraction", type=float, default=0.001)
    parser.add_argument("--max-abs-dc", type=float, default=0.05)
    parser.add_argument("--fail-on-silence", action="store_true")
    args = parser.parse_args()
    if not 0 <= args.max_clipped_fraction <= 1:
        parser.error("--max-clipped-fraction must be between 0 and 1")
    if not 0 <= args.max_abs_dc <= 1:
        parser.error("--max-abs-dc must be between 0 and 1")
    try:
        result = analyze(args.wav)
    except (OSError, EOFError, ValueError, wave.Error) as exc:
        parser.error(str(exc))
    violations = []
    if result["sample_rate_hz"] != args.expected_rate:
        violations.append("unexpected sample rate")
    for item in result["per_channel"]:
        c = item["channel"]
        if item["clipped_fraction"] > args.max_clipped_fraction:
            violations.append(f"channel {c}: clipping threshold exceeded")
        if abs(item["dc_offset"]) > args.max_abs_dc:
            violations.append(f"channel {c}: DC threshold exceeded")
        if args.fail_on_silence and item["silent"]:
            violations.append(f"channel {c}: silent")
    result["pass"] = not violations
    result["violations"] = violations
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
