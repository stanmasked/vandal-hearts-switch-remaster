#!/usr/bin/env python3
"""Inspect raw NeXium virtual-sink PCM; measurements, not audible music proof."""
from __future__ import annotations
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sys

SCHEMA = "vh-nexium-pcm-quality/v1"
RATE = 48000
CHANNELS = 2
SILENCE_RMS = 32.0
WINDOW_FRAMES = 4800  # 100 ms


class PcmFormatError(ValueError):
    pass


def analyze(path: Path, *, expected_sha256: str | None = None) -> dict:
    if not path.is_file() or path.is_symlink():
        raise PcmFormatError("raw PCM must be an existing regular file, not a symlink")
    data = path.read_bytes()
    if not data or len(data) % 4:
        raise PcmFormatError("PCM must contain complete nonempty stereo s16le frames")
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise PcmFormatError("raw PCM SHA-256 differs from pinned evidence")
    values = array("h")
    values.frombytes(data)
    if sys.byteorder != "little":
        values.byteswap()
    frames = len(values) // CHANNELS
    totals = [0, 0]
    square_totals = [0, 0]
    peaks = [0, 0]
    clipped = [0, 0]
    differences = 0
    cross = 0
    for i in range(0, len(values), 2):
        left, right = values[i], values[i + 1]
        for c, v in enumerate((left, right)):
            totals[c] += v
            square_totals[c] += v * v
            peaks[c] = max(peaks[c], abs(v))
            clipped[c] += abs(v) >= 32767
        differences += (left - right) ** 2
        cross += left * right
    window_rms = []
    low_run = longest_low = 0
    windows_low = 0
    for start in range(0, frames, WINDOW_FRAMES):
        end = min(frames, start + WINDOW_FRAMES)
        n = (end - start) * CHANNELS
        energy = sum(v * v for v in values[start * 2:end * 2])
        rms = math.sqrt(energy / n)
        window_rms.append(round(rms, 3))
        if rms < SILENCE_RMS:
            low_run += end - start
            longest_low = max(longest_low, low_run)
            windows_low += 1
        else:
            low_run = 0
    mean = [v / frames for v in totals]
    variance = [square_totals[c] / frames - mean[c] ** 2 for c in range(2)]
    correlation_den = math.sqrt(max(variance[0], 0) * max(variance[1], 0))
    correlation = ((cross / frames - mean[0] * mean[1]) / correlation_den
                   if correlation_den else None)
    return {
        "schema": SCHEMA,
        "scope": "Virtual PulseAudio monitor of NeXium; waveform identity and hearing are not established",
        "hardware_status": "HARDWARE NOT TESTED",
        "pcm_sha256": digest,
        "format": "s16le stereo 48000 Hz",
        "bytes": len(data),
        "frames": frames,
        "duration_seconds": round(frames / RATE, 3),
        "rms_by_channel": [round(math.sqrt(v / frames), 3) for v in square_totals],
        "peak_by_channel": peaks,
        "mean_dc_by_channel": [round(v, 3) for v in mean],
        "full_scale_clipped_samples_by_channel": clipped,
        "channel_difference_rms": round(math.sqrt(differences / frames), 3),
        "channel_correlation": round(correlation, 4) if correlation is not None else None,
        "window_frames": WINDOW_FRAMES,
        "window_silence_rms_threshold": SILENCE_RMS,
        "window_count": len(window_rms),
        "low_rms_window_count": windows_low,
        "longest_contiguous_low_rms_seconds": round(longest_low / RATE, 3),
        "window_rms": window_rms,
        "observation": "NONZERO_MONITOR_PCM" if any(peaks) else "MONITOR_SILENCE",
        "audible_music_confirmed": False,
        "original_soundtrack_confirmed": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pcm", type=Path)
    p.add_argument("--expected-sha256")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    try:
        result = analyze(args.pcm, expected_sha256=args.expected_sha256)
        payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            if args.output.exists() or args.output.is_symlink():
                raise PcmFormatError("refuse overwrite of existing output")
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0
    except (PcmFormatError, OSError) as e:
        print(json.dumps({"result": "INVALID_PCM", "error": str(e)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
