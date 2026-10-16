"""Validate a native diagnostic WAV's structural invariants and payload fingerprint.

Avoids fixed golden audio bytes: hashes are observational and reproducibility
is verified by CI's byte-for-byte comparison of separate native renders.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path


def inspect(path: Path):
    raw = path.read_bytes()
    if len(raw) < 44 or raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError("not canonical WAV")
    riff_size = struct.unpack_from("<I", raw, 4)[0]
    if riff_size + 8 != len(raw):
        raise ValueError("RIFF size differs from physical file length")
    # Exporter deliberately writes the canonical 44-byte PCM header.
    if raw[12:16] != b"fmt " or struct.unpack_from("<I", raw, 16)[0] != 16:
        raise ValueError("unexpected fmt chunk")
    audio_format, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", raw, 20)
    if (audio_format, channels, rate, byte_rate, align, bits) != (1, 2, 48000, 192000, 4, 16):
        raise ValueError("unexpected PCM transport format")
    if raw[36:40] != b"data":
        raise ValueError("missing canonical data chunk")
    data_size = struct.unpack_from("<I", raw, 40)[0]
    if data_size != len(raw) - 44 or data_size % 4:
        raise ValueError("WAV data size/alignment mismatch")
    frames = data_size // 4
    # 128 blocks x 512 frames at 44.1kHz, resampled to 48kHz.
    if not 71300 <= frames <= 71350:
        raise ValueError("unexpected resampler output frame count")
    return {
        "frames": frames,
        "duration_seconds": round(frames / 48000, 6),
        "payload_sha256": hashlib.sha256(raw[44:]).hexdigest(),
        "container_sha256": hashlib.sha256(raw).hexdigest(),
        "source": "generated native C SEQ/SPU/resampler fixture",
        "original_game_audio_verified": False,
        "audible_console_output_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", type=Path)
    args = parser.parse_args()
    try:
        report = inspect(args.wav)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
