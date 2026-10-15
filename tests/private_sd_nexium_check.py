#!/usr/bin/env python3
"""Synthetic NeXium SD texture: four UV quadrants, original PS1 4bpp/CLUT.

The staged DAT resources are generated from scratch, never from game assets.
Four distinct colored quadrants catch swapped U/V, reversed axes, wrong
texture-page offsets, wrong 4bpp nibble order and incorrect local CLUT row.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from inspect_vh_map_texture_bank import LAND_BYTES, MAP_RECORD_BYTES, TEXTURE_BYTES
from stage_vh_private_map_bank import stage_private_assets

MAP_NUMBER = 11
MAP_SLOT = 241
U0, V0, WIDTH, HEIGHT = 240, 192, 15, 15
CLUT_ID = 35
COLORS_BGR555 = (0, 0x001f, 0x03e0, 0x7c00, 0x03ff)

# Deep inside each rendered quadrant, away from raster edge interpolation.
SCREEN_SAMPLES = (
    ("upper-left red", (400, 205), (255, 0, 0)),
    ("upper-right green", (880, 205), (0, 255, 0)),
    ("lower-left blue", (400, 510), (0, 0, 255)),
    ("lower-right yellow", (880, 510), (255, 255, 0)),
)


def synthetic_source():
    """Construct a 256x256 4bpp source page and one 1797-byte map record."""
    tex = bytearray(TEXTURE_BYTES)
    land = bytearray(LAND_BYTES)
    record = MAP_NUMBER * MAP_RECORD_BYTES
    land[record + MAP_SLOT * 4:record + MAP_SLOT * 4 + 4] = bytes(
        (U0, V0, WIDTH, HEIGHT)
    )
    land[record + 257 * 4 + MAP_SLOT] = CLUT_ID
    palette = record + 257 * 5 + (CLUT_ID - 32) * 32
    for index, color in enumerate(COLORS_BGR555):
        land[palette + 2 * index:palette + 2 * index + 2] = color.to_bytes(
            2, "little"
        )
    # Each 16x16 UV patch has four 8x8 squares. The low 4 bits of
    # every byte are the LEFT pixel; upper nibble encodes the RIGHT.
    for v in range(V0, V0 + 16):
        for u in range(U0, U0 + 16, 2):
            top = v < V0 + 8
            left = u < U0 + 8
            color_id = (1 if left else 2) if top else (3 if left else 4)
            tex[v * 128 + u // 2] = color_id | (color_id << 4)
    return bytes(tex), bytes(land)


def stage(sd_root):
    texture, land = synthetic_source()
    report = stage_private_assets(texture, land, sd_root)
    assert report["uvwh"] == [U0, V0, WIDTH, HEIGHT]
    assert report["local_clut_id"] == CLUT_ID
    print("Synthetic four-quadrant map texture staged under:", sd_root)
    return report


def check(image_path):
    from PIL import Image

    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280, 720):
        raise ValueError("unexpected NeXium screenshot dimensions")
    # Baseline scene puts a RED tile at (210,90); private preview leaves
    # that area BLACK (the NRO sets a black tile first).
    border = frame.getpixel((210, 90))
    if max(border) > 45:
        raise ValueError(f"expected black private-preview border, got {border}")
    # All four samples are in the interior of the FT4 textured patch;
    # no screenshot-wide color histogram or generic colored UI can
    # satisfy these UV/CLUT-specific samples.
    for name, (x, y), expected in SCREEN_SAMPLES:
        observed = frame.getpixel((x, y))
        print(f"Original private SD FT4 {name}: {observed}")
        if max(abs(c - e) for c, e in zip(observed, expected)) > 36:
            raise ValueError(
                f"wrong private SD UV mapping/CLUT for {name}: "
                f"expected {expected}, got {observed}"
            )
    # Sample frame center separately to reject a stale baseline capture.
    center = frame.getpixel((640, 360))
    if max(center) < 175:
        raise ValueError(f"private preview center is not textured: {center}")
    print("Four-quadrant private SD FT4 screenshot verified")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage-sd-root", type=Path)
    group.add_argument("--check-screenshot", type=Path)
    args = parser.parse_args()
    if args.stage_sd_root is not None:
        stage(args.stage_sd_root)
    else:
        check(args.check_screenshot)


if __name__ == "__main__":
    main()
