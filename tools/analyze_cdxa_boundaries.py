#!/usr/bin/env python3
"""Report PCM jumps at consecutive decoded CD-XA sector boundaries (read-only).

A large jump is a diagnostic clue, NOT proof of an audible click or bad XA decode.
"""
from __future__ import annotations

import argparse
import heapq
import json
import struct
import wave
from pathlib import Path

from tools.validate_cdxa_extraction import (
    PCM_FRAMES_PER_SECTOR, validate_extraction,
)


def analyze_boundaries(
    report_path: Path, payload_path: Path, wav_path: Path,
    threshold: int = 8192, top: int = 10,
) -> dict[str, object]:
    if not 0 <= threshold <= 65535:
        raise ValueError("threshold must be between 0 and 65535")
    if top < 1:
        raise ValueError("top must be positive")
    validated = validate_extraction(report_path, payload_path, wav_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    lbas = report["audio_lbas"]
    largest: list[tuple[int, int, dict[str, object]]] = []
    flagged = 0
    total = max(0, len(lbas) - 1)
    with wave.open(str(wav_path), "rb") as pcm:
        for index in range(1, len(lbas)):
            pcm.setpos(index * PCM_FRAMES_PER_SECTOR - 1)
            frames = pcm.readframes(2)
            if len(frames) != 8:
                raise ValueError(f"incomplete PCM near sector boundary {index}")
            old_left, old_right, new_left, new_right = struct.unpack("<hhhh", frames)
            left_jump = abs(new_left - old_left)
            right_jump = abs(new_right - old_right)
            jump = max(left_jump, right_jump)
            if jump >= threshold:
                flagged += 1
            if top:
                item = {
                    "boundary_index": index,
                    "previous_lba": lbas[index - 1],
                    "next_lba": lbas[index],
                    "missing_source_sectors": lbas[index] - lbas[index - 1] - 1,
                    "left_jump": left_jump,
                    "right_jump": right_jump,
                    "max_jump": jump,
                }
                entry = (jump, index, item)
                if len(largest) < top:
                    heapq.heappush(largest, entry)
                elif (jump, index) > largest[0][:2]:
                    heapq.heapreplace(largest, entry)
    return {
        "audio_sectors": validated["audio_sectors"],
        "boundaries_checked": total,
        "jump_threshold": threshold,
        "boundaries_at_or_above_threshold": flagged,
        "largest_boundaries": [
            item for _, _, item in sorted(largest, key=lambda x: (-x[0], x[1]))
        ],
        "warning": (
            "PCM jumps do not prove audible defects. This does not reconstruct "
            "original CD-XA interleave or playback timing."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("payload", type=Path)
    parser.add_argument("wav", type=Path)
    parser.add_argument("--threshold", type=int, default=8192)
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()
    try:
        result = analyze_boundaries(
            args.report, args.payload, args.wav, args.threshold, args.top
        )
    except (OSError, ValueError, EOFError, wave.Error, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
