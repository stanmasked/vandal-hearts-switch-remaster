#!/usr/bin/env python3
"""Check two emulator screenshots of the independent native AV NRO.

This checks graphics and animation only. A green audout status is a
synchronous initialization/worker indicator, never proof of heard audio.
"""
import argparse
import json
from pathlib import Path
from PIL import Image

WIDTH, HEIGHT = 1280, 720
HERO = (86, 190, 244)
AUDIO_OK = (60, 211, 138)
AUDIO_FAIL = (250, 108, 90)


def near(color, expected, tolerance=25):
    return max(abs(a-b) for a,b in zip(color, expected)) <= tolerance


def inspect_images(first: Image.Image, second: Image.Image) -> dict:
    first = first.convert("RGB")
    second = second.convert("RGB")
    if first.size != (WIDTH, HEIGHT) or second.size != (WIDTH, HEIGHT):
        raise ValueError("unexpected emulator screenshot dimensions")
    center = first.getpixel((452, 296))
    if not near(center, HERO):
        raise ValueError(f"hero marker absent at expected grid coordinate: {center}")
    audio_sample = first.getpixel((108, 104))
    red, green, blue = audio_sample
    # Some emulator capture paths transform the blue component of the
    # libnx RGBA8 status fill (one observed green pixel was 60,212,91).
    # Recognize the intended green-vs-red signal by channel dominance,
    # without accepting dark backgrounds, grayscale, or arbitrary colors.
    green_signal = (green >= 155 and green > red + 70
                    and green > blue + 40)
    red_signal = (red >= 145 and red > green + 40
                  and red > blue + 40)
    status = ("initialized" if green_signal else
              "unavailable_or_error" if red_signal else "unknown")
    if status == "unknown":
        raise ValueError(f"audio-service status marker absent: {audio_sample}")

    # Sample only the heartbeat; animated bar is separate from the cursor,
    # so its change demonstrates video-loop progress without emulated input.
    before = first.crop((70, 610, 870, 624))
    after = second.crop((70, 610, 870, 624))
    changed = sum(1 for a,b in zip(before.getdata(), after.getdata())
                  if max(abs(x-y) for x,y in zip(a,b)) > 20)
    if changed < 16:
        raise ValueError(f"framebuffer heartbeat did not advance: changed={changed}")
    return {
        "video_framebuffer": "observed",
        "grid_hero_marker": "observed",
        "heartbeat_changed_pixels": changed,
        "audout_status": status,
        "audible_audio_verified": False,
        "actual_gameplay_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    try:
        with Image.open(args.before) as first, Image.open(args.after) as second:
            report = inspect_images(first, second)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
