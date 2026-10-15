#!/usr/bin/env python3
"""Measure decoded CD-XA stereo PCM WAV signal statistics without changing it.

Diagnostic only: silence and full-scale samples do not independently prove
an extraction, decoding, or audio quality failure.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path

CHUNK_FRAMES = 4096
FULL_SCALE = 32768


def analyze_wav(path: Path) -> dict[str, object]:
    try:
        with wave.open(str(path), "rb") as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                    wav.getcomptype()) != (2, 2, 37800, "NONE"):
                raise ValueError("WAV must be uncompressed stereo 16-bit PCM at 37800 Hz")
            count = wav.getnframes()
            if count <= 0:
                raise ValueError("WAV has no PCM frames")
            squares = [0, 0]
            peaks = [0, 0]
            zero_samples = [0, 0]
            full_scale_samples = [0, 0]
            zero_frames = 0
            for start in range(0, count, CHUNK_FRAMES):
                frames = min(CHUNK_FRAMES, count - start)
                data = wav.readframes(frames)
                if len(data) != frames * 4:
                    raise ValueError(f"truncated PCM at frame {start}")
                samples = struct.unpack("<" + "h" * (frames * 2), data)
                for i in range(frames):
                    a = samples[i * 2]
                    b = samples[i * 2 + 1]
                    if a == 0 and b == 0:
                        zero_frames += 1
                    for channel, value in enumerate((a, b)):
                        magnitude = abs(value)
                        squares[channel] += value * value
                        peaks[channel] = max(peaks[channel], magnitude)
                        zero_samples[channel] += int(value == 0)
                        full_scale_samples[channel] += int(value in (-32768, 32767))
            return {
                "frames": count,
                "sample_rate": 37800,
                "peak_abs_sample": peaks,
                "rms_amplitude": [math.sqrt(value / count) for value in squares],
                "zero_sample_fraction": [value / count for value in zero_samples],
                "full_scale_sample_count": full_scale_samples,
                "silent_stereo_frame_fraction": zero_frames / count,
                "warning": (
                    "PCM statistics are diagnostic only: legitimate audio may contain "
                    "silence or full-scale samples, and nonzero output does not prove faithful decoding."
                ),
            }
    except (EOFError, wave.Error) as error:
        raise ValueError(f"invalid WAV input: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    args = parser.parse_args()
    try:
        result = analyze_wav(args.wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
