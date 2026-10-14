#!/usr/bin/env python3
"""Convert a 2048-byte-sector PS1 STR extraction to a restored MP4.

Requires Python 3 and FFmpeg with the psxstr demuxer and MDEC decoder.
Input must be an extracted 2048-byte-sector stream (such as TITLE_WS.STR),
not a complete BIN/CUE disc image.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

SECTOR_SIZE = 2048
RAW_CD_SECTOR_SIZE = 2352
STR_MAGIC = b"\x60\x01\x01\x80"


def repack(source: Path, destination: Path) -> tuple[int, int]:
    # Refuse in-place conversion: opening destination would truncate source data.
    if source.resolve() == destination.resolve():
        raise ValueError("Input and output paths must be different.")
    size = source.stat().st_size
    if size % SECTOR_SIZE:
        raise ValueError(
            f"Input size {size} is not divisible by {SECTOR_SIZE}; "
            "expected a 2048-byte-sector extraction."
        )
    sectors = size // SECTOR_SIZE
    video_sectors = 0
    with source.open("rb") as src, destination.open("wb") as dst:
        for _ in range(sectors):
            payload = src.read(SECTOR_SIZE)
            is_video = payload.startswith(STR_MAGIC)
            video_sectors += int(is_video)
            submode = 0x02 if is_video else 0x00
            header = (
                b"\x00" + b"\xff" * 10 + b"\x00"
                + bytes((0, 0, 0, 2))
                + bytes((0, 0, submode, 0)) * 2
            )
            sector = header + payload
            dst.write(sector + b"\x00" * (RAW_CD_SECTOR_SIZE - len(sector)))
    return sectors, video_sectors


def encode(ffmpeg: str, raw: Path, output: Path, width: int, height: int, crf: int) -> None:
    command = [
        ffmpeg, "-y", "-v", "warning", "-f", "psxstr", "-i", str(raw),
        "-map", "0:v:0", "-an",
        "-vf",
        f"hqdn3d=1.2:1.2:4:4,scale={width}:{height}:flags=lanczos,"
        "unsharp=5:5:0.35:3:3:0.0",
        "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output),
    ]
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="extracted .STR stream")
    parser.add_argument("-o", "--output", type=Path, default=Path("TITLE_WS_restored_720p.mp4"))
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--crf", type=int, default=17)
    parser.add_argument("--keep-intermediate", action="store_true")
    args = parser.parse_args()

    if args.width <= 0 or args.height <= 0:
        parser.error("--width and --height must be positive integers.")
    if not 0 <= args.crf <= 51:
        parser.error("--crf must be between 0 and 51.")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        parser.error("FFmpeg was not found on PATH.")
    source = args.input.resolve()
    output = args.output.resolve()
    if source == output:
        parser.error("Input and output paths must be different.")
    if not source.is_file():
        parser.error(f"Input file not found: {source}")
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.keep_intermediate:
        raw = output.with_name(output.stem + "_repacked.str")
        sectors, video_sectors = repack(source, raw)
        print(f"Repacked {sectors} sectors ({video_sectors} video-tagged).")
        encode(ffmpeg, raw, output, args.width, args.height, args.crf)
    else:
        with tempfile.TemporaryDirectory(prefix="psxstr_") as temp_dir:
            raw = Path(temp_dir) / "repacked.str"
            sectors, video_sectors = repack(source, raw)
            print(f"Repacked {sectors} sectors ({video_sectors} video-tagged).")
            encode(ffmpeg, raw, output, args.width, args.height, args.crf)
    print(f"Wrote: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
