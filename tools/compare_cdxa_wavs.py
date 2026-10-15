#!/usr/bin/env python3
"""Compare PCM samples from two stereo 16-bit WAV files, without modifying them."""
from __future__ import annotations

import argparse
import json
import struct
import wave
from pathlib import Path

CHUNK_FRAMES = 4096


def compare_wavs(candidate: Path, reference: Path) -> dict[str, object]:
    try:
        with wave.open(str(candidate), "rb") as left, wave.open(str(reference), "rb") as right:
            expected = (2, 2, 37800, "NONE")
            for label, wav in (("candidate", left), ("reference", right)):
                actual = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype())
                if actual != expected:
                    raise ValueError(f"{label} must be uncompressed stereo 16-bit PCM at 37800 Hz; got {actual}")
            frames = left.getnframes()
            if right.getnframes() != frames:
                raise ValueError(f"WAV frame count mismatch: candidate={frames}, reference={right.getnframes()}")
            different_frames = 0
            different_samples = 0
            max_abs_difference = 0
            first_difference = None
            absolute_sum = 0
            for start in range(0, frames, CHUNK_FRAMES):
                size = min(CHUNK_FRAMES, frames - start)
                a = left.readframes(size)
                b = right.readframes(size)
                if len(a) != size * 4 or len(b) != size * 4:
                    raise ValueError(f"truncated PCM at frame {start}")
                if a == b:
                    continue
                samples_a = struct.unpack("<" + "h" * (size * 2), a)
                samples_b = struct.unpack("<" + "h" * (size * 2), b)
                for offset in range(size):
                    dl = abs(samples_a[2 * offset] - samples_b[2 * offset])
                    dr = abs(samples_a[2 * offset + 1] - samples_b[2 * offset + 1])
                    if dl or dr:
                        different_frames += 1
                        if first_difference is None:
                            first_difference = start + offset
                    different_samples += int(dl != 0) + int(dr != 0)
                    max_abs_difference = max(max_abs_difference, dl, dr)
                    absolute_sum += dl + dr
            return {
                "exact_match": different_frames == 0,
                "frames_compared": frames,
                "different_frames": different_frames,
                "different_channel_samples": different_samples,
                "first_different_frame": first_difference,
                "max_absolute_sample_difference": max_abs_difference,
                "mean_absolute_sample_difference": absolute_sum / (frames * 2) if frames else 0,
                "warning": "A numerical match alone does not confirm XA extraction timing, stream selection or audible fidelity.",
            }
    except (EOFError, wave.Error) as error:
        raise ValueError(f"invalid WAV input: {error}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--require-exact", action="store_true", help="exit nonzero if samples differ")
    args = parser.parse_args()
    try:
        result = compare_wavs(args.candidate, args.reference)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0 if result["exact_match"] or not args.require_exact else 1


if __name__ == "__main__":
    raise SystemExit(main())
