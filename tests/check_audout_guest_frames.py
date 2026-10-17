#!/usr/bin/env python3
"""Fail-closed *visual* NeXium guest-liveness check for audout NRO.

This observes framebuffer differences only. It does NOT verify audout,
returned PCM descriptors, physical sound, ZL/ZR input, or HOME behavior.
Screenshots are already captured by the CI runner (no OCR or audio).
"""
import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def inspect_guest_frames(first: Image.Image, second: Image.Image) -> dict:
    if first.size != second.size:
        raise ValueError("guest screenshots must have matching dimensions")
    width, height = first.size
    if width < 640 or height < 360:
        raise ValueError("unexpectedly small emulator screenshot")
    # Trim the window edges and borders to exclude window-manager chrome.
    frame = (24, 24, width - 24, height - 24)
    before = first.convert("RGB").crop(frame)
    after = second.convert("RGB").crop(frame)
    if (max(ImageStat.Stat(before).stddev) < 4.0 or
            max(ImageStat.Stat(after).stddev) < 4.0):
        raise ValueError("guest image missing meaningful visual detail")
    diff = ImageChops.difference(before, after)
    # A single changed pixel or cursor animation is not useful progress.
    # The black-and-white bitmap counts pixels that differ by >=24 RGB
    # intensity on at least one channel. This is NOT a PCM/audio metric.
    changed = 0
    # Pillow 14 removes getdata(); keep compatibility with older Pillow
    # versions used by existing CI runners.
    pixels = (diff.get_flattened_data() if
              hasattr(diff, "get_flattened_data") else diff.getdata())
    for pixel in pixels:
        if max(pixel) >= 24:
            changed += 1
    if changed < 80:
        raise ValueError("guest framebuffer did not visibly progress")
    return {
        "guest_framebuffer": "visibly_changed",
        "changed_pixels": changed,
        "image_width": width,
        "image_height": height,
        "audout_initialized_verified": False,
        "pcm_return_verified": False,
        "zr_injection_verified": False,
        "zl_injection_verified": False,
        "home_resume_verified": False,
        "audible_audio_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        with Image.open(args.before) as before, Image.open(args.after) as after:
            report = inspect_guest_frames(before, after)
    except (OSError, ValueError) as err:
        parser.error(str(err))
    payload = json.dumps(report, indent=2) + "\n"
    print(payload, end="")
    if args.json_out is not None:
        args.json_out.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
