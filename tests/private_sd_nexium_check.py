#!/usr/bin/env python3
"""Asset-free NeXium private-SD smoke fixture + screenshot checker.

Both functions only use synthetic color-strip texture/palette data.
Nothing from original game images is loaded or committed.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_texture_bank import (  # noqa: E402
    LAND_BYTES, MAP_RECORD_BYTES, TEXTURE_BYTES,
)
from stage_vh_private_map_bank import stage_private_assets  # noqa: E402


def stage(sd_root):
    tex = bytearray(TEXTURE_BYTES)
    land = bytearray(LAND_BYTES)
    record = 11 * MAP_RECORD_BYTES
    slot = 241
    land[record + slot * 4:record + slot * 4 + 4] = bytes((240,192,15,15))
    land[record + 257 * 4 + slot] = 35
    palette = record + 257 * 5 + (35 - 32) * 32
    land[palette + 2:palette + 6] = bytes((0x1f,0,0xe0,0x03))
    for v in range(192,208):
        for u in range(240,256,2):
            tex[v * 128 + u // 2] = 0x21
    report = stage_private_assets(bytes(tex), bytes(land), sd_root)
    assert report["uvwh"] == [240,192,15,15]
    assert report["local_clut_id"] == 35
    print("Synthetic-only NeXium SD fixture staged:", sd_root)


def check(image_path):
    from PIL import Image
    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280, 720):
        raise ValueError("unexpected NeXium screenshot dimensions")
    # Discriminate the PRIVATE preview from the baseline raster probes.
    # Baseline has a bright red TILE at (210,90) and a dynamic gray
    # background at the center; private mode draws a black border and
    # the full color-strip POLY_FT4 patch across the center.
    border = frame.getpixel((210, 90))
    center = frame.getpixel((640, 360))
    border_is_black = max(border) <= 45
    center_is_texel = (
        center[0] >= 215 and center[1] <= 45 and center[2] <= 45
    ) or (
        center[1] >= 215 and center[0] <= 45 and center[2] <= 45
    )
    print("Private preview border / center RGB:", border, center)
    if not border_is_black or not center_is_texel:
        raise ValueError("NRO still shows baseline synthetic scene, not SD preview")
    # Only the isolated FT4 patch at native x1..11, y1..8 covers this
    # region. Do not count the NeXium menu, toolbar or emulator background.
    pixels = frame.crop((230,110,1050,630)).getdata()
    red = sum(r >= 215 and g <= 45 and b <= 45 for r,g,b in pixels)
    green = sum(g >= 215 and r <= 45 and b <= 45 for r,g,b in
                frame.crop((230,110,1050,630)).getdata())
    print("Original private POLY_FT4 screenshot red / green:", red, green)
    if red < 100 or green < 100:
        raise ValueError("private synthetic texture patch not visible")
    return red, green


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage-sd-root", type=Path)
    group.add_argument("--check-screenshot", type=Path)
    args = parser.parse_args()
    if args.stage_sd_root:
        stage(args.stage_sd_root)
    else:
        check(args.check_screenshot)


if __name__ == "__main__":
    main()
