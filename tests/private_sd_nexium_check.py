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
    # A second, independently authored face uses slot 242 / CLUT ID 36
    # in a DIFFERENT source page rectangle. The single-patch scene still
    # uses only slot 241, so its existing four-color proof is unchanged.
    land[record + 242 * 4:record + 242 * 4 + 4] = bytes((224,192,15,15))
    land[record + 257 * 4 + 242] = 36
    alternate = record + 257 * 5 + (36 - 32) * 32
    land[alternate + 2:alternate + 6] = bytes((0x1f,0x7c,0xe0,0x7f))
    for v in range(192, 208):
        for u in range(224, 240, 2):
            index = 1 if v < 200 else 2
            tex[v * 128 + u // 2] = index | (index << 4)
    # Each 16x16 UV patch has four 8x8 squares. The low 4 bits of
    # every byte are the LEFT pixel; upper nibble encodes the RIGHT.
    for v in range(V0, V0 + 16):
        for u in range(U0, U0 + 16, 2):
            top = v < V0 + 8
            left = u < U0 + 8
            color_id = (1 if left else 2) if top else (3 if left else 4)
            tex[v * 128 + u // 2] = color_id | (color_id << 4)
    return bytes(tex), bytes(land)


def synthetic_geometry_models():
    """336 exact 304-byte map tiles; tile (6,3) has TWO textured faces."""
    from inspect_vh_map_geometry import (
        MAP_11_BYTES, MAP_11_STRIDE, TILE_BYTES, VERTICES_BYTES,
        GFX_BYTES, FACE_BYTES,
    )
    models = bytearray(MAP_11_BYTES)
    tile_base = (3 * MAP_11_STRIDE + 6) * TILE_BYTES
    points = (
        (-32, 0, -16), (0, 0, -16), (-32, 0, 24), (0, 0, 24),
        (0, 0, -16), (32, 0, -16), (0, 0, 24), (32, 0, 24),
    )
    for i, (vx, vy, vz) in enumerate(points):
        models[tile_base + i * 8:tile_base + i * 8 + 8] = (
            int(vx).to_bytes(2, "little", signed=True) +
            int(vy).to_bytes(2, "little", signed=True) +
            int(vz).to_bytes(2, "little", signed=True) + bytes(2)
        )
    # Source RenderMapTile maps face vertices 0/1/2/3 to
    # FT4 packet 0/1/3/2. Source vertex 2 is bottom-right.
    for n, (gfx, ids) in enumerate(((241, (0,1,3,2)), (242, (4,5,7,6)))):
        gfx_at = tile_base + VERTICES_BYTES + n * 2
        models[gfx_at:gfx_at + 2] = gfx.to_bytes(2, "little")
        faces_at = tile_base + VERTICES_BYTES + GFX_BYTES + n * 4
        models[faces_at:faces_at + 4] = bytes(ids)
        models[tile_base + VERTICES_BYTES + GFX_BYTES +
               FACE_BYTES + n] = n + 1
    models[tile_base + TILE_BYTES - 2] = 2
    models[tile_base + TILE_BYTES - 1] = 4
    return bytes(models)


def stage_geometry(sd_root):
    from stage_vh_private_map_geometry import stage_map11_geometry
    metadata = stage_map11_geometry(synthetic_geometry_models(), sd_root)
    assert metadata["active_faces"] == 2
    assert metadata["populated_tiles"] == 1
    print("Staged TWO independent MapTileModel FT4 source faces")
    return metadata

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



def check_geometry(image_path):
    from PIL import Image
    frame = Image.open(image_path).convert("RGB")
    if frame.size != (1280, 720):
        raise ValueError("unexpected private geometry screenshot size")
    # Actual pinned GTE RTPT/RTPS perspective (not old orthographic
    # projection): with pitch -512, H=14, Z=96, the first face projects
    # TL=(0,1), TR=(6,1), BL=(2,6), BR=(6,6) in native 12x9 pixels.
    # The formerly checked (210,90) now LIES INSIDE the upper quad.
    border = frame.getpixel((50, 40))
    if max(border) > 45:
        raise ValueError("GTE geometry upper border is not black")
    probes = (
        ("left top red", (260,210), (255,0,0)),
        ("right top magenta", (850,210), (255,0,255)),
        ("left bottom blue", (400,400), (0,0,255)),
        ("right bottom cyan", (850,400), (0,255,255)),
        # Old orthographic geometry began at native (2,2), around
        # screen (320,160); genuine GTE projection puts a red top
        # edge at (300,125), which the former scene left black.
        ("perspective-only red upper edge", (300,125), (255,0,0)),
    )
    for title, (x,y), expected in probes:
        pixel = frame.getpixel((x,y))
        print("Original geometry FT4", title, pixel)
        if max(abs(a-b) for a,b in zip(pixel,expected)) > 36:
            raise ValueError(f"wrong {title} : {pixel}, expected {expected}")
    print("Private SD MapTileModel two-face geometry screenshot verified")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stage-sd-root", type=Path)
    group.add_argument("--check-screenshot", type=Path)
    group.add_argument("--stage-geometry-sd-root", type=Path)
    group.add_argument("--check-geometry-screenshot", type=Path)
    args = parser.parse_args()
    if args.stage_sd_root is not None:
        stage(args.stage_sd_root)
    elif args.stage_geometry_sd_root is not None:
        stage_geometry(args.stage_geometry_sd_root)
    elif args.check_geometry_screenshot is not None:
        check_geometry(args.check_geometry_screenshot)
    else:
        check(args.check_screenshot)


if __name__ == "__main__":
    main()
