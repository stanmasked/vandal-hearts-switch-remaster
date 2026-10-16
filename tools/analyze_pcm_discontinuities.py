#!/usr/bin/env python3
"""Report sample-to-sample PCM jumps, with 512-source-frame boundary probes.

This is a diagnostic, not a definitive audible-click detector. Legitimate
transients can cause large differences. Only a user-chosen limit makes it fail.
"""
import argparse
import json
import struct
import wave
from pathlib import Path


def analyze(path: Path, *, input_block_frames: int = 512):
    if input_block_frames <= 0:
        raise ValueError("input block size must be positive")
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                wav.getcomptype()) != (2, 2, 48000, "NONE"):
            raise ValueError("requires stereo PCM16 48000 Hz WAV")
        count = wav.getnframes()
        data = wav.readframes(count)
    if len(data) != 4 * count or count < 2:
        raise ValueError("truncated or too short PCM data")
    samples = struct.unpack("<" + "h" * (count * 2), data)
    jumps = [0, 0]
    largest = [0, 0]
    boundaries = []
    # Nominal positions at which 44.1-kHz source block boundaries occur
    # in the ideal 48-kHz frame timeline. The actual output may use
    # neighboring frames for interpolation, hence a +/-2-frame window.
    b = 1
    while True:
        location = round(b * input_block_frames * 48000 / 44100)
        if location >= count:
            break
        boundaries.append(location)
        b += 1
    boundary_max = [0, 0]
    for frame in range(1, count):
        for ch in range(2):
            difference = abs(samples[2 * frame + ch] - samples[2 * (frame - 1) + ch])
            if difference > largest[ch]:
                largest[ch] = difference
                jumps[ch] = frame
    for center in boundaries:
        for frame in range(max(1, center - 2), min(count, center + 3)):
            for ch in range(2):
                difference = abs(samples[2 * frame + ch] - samples[2 * (frame - 1) + ch])
                boundary_max[ch] = max(boundary_max[ch], difference)
    return {
        "frames": count, "boundaries_inspected": len(boundaries),
        "max_adjacent_delta": largest, "max_delta_frame": jumps,
        "max_boundary_window_delta": boundary_max,
        "boundary_window_radius_frames": 2,
        "note": "Large deltas can be musical transients, not necessarily defects",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("wav", type=Path)
    ap.add_argument("--max-delta", type=int, help="Optional per-channel delta limit, 0..65535")
    args = ap.parse_args()
    if args.max_delta is not None and not 0 <= args.max_delta <= 65535:
        ap.error("--max-delta must be 0..65535")
    try:
        report = analyze(args.wav)
    except (OSError, ValueError, EOFError, wave.Error) as exc:
        ap.error(str(exc))
    report["passed_optional_limit"] = (
        args.max_delta is None or max(report["max_adjacent_delta"]) <= args.max_delta
    )
    print(json.dumps(report, indent=2))
    return 0 if report["passed_optional_limit"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
