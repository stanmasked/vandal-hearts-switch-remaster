#!/usr/bin/env python3
"""Read-only inspector for a DECOMPRESSED Vandal Hearts map 11 tile model slab.

Source: pinned upstream include/field.h::MapTileModel,
src/states/game_setup.c::LoadMap case 11 and src/core/graphics.c::RenderMapTile.

Input is a raw, ALREADY DECOMPRESSED, contiguous tile array, NOT M_MAP02.PRS.
The game's M_MAP02.PRS stream has a compressed wrapper and must be decoded
separately with bounded output before it can be passed to this inspector.
No copyrighted map bytes or decompression bypass are included.
"""
import argparse
import collections
import json
from pathlib import Path
import struct

from inspect_vh_map_texture_bank import (
    LAND_BYTES, MAP_COUNT, MAP_RECORD_BYTES, SLOT_COUNT,
)

VERTEX_COUNT = 22
FACE_COUNT = 18
VERTEX_BYTES = 8                 # signed x/y/z and signed pad, four 16-bit words
VERTICES_BYTES = VERTEX_COUNT * VERTEX_BYTES
GFX_BYTES = FACE_COUNT * 2       # s16[18], local map-texture slot IDs
FACE_BYTES = FACE_COUNT * 4      # u8 faces[18][4]
SHADES_BYTES = FACE_COUNT        # u8 shades[18]
TILE_BYTES = VERTICES_BYTES + GFX_BYTES + FACE_BYTES + SHADES_BYTES + 2
MAP_11_STRIDE = 28               # original gMapDataSizeX
MAP_11_ROWS = 12                 # original gMapDataSizeZ
MAP_11_ACTIVE_WIDTH = 24        # original gMapSizeX
MAP_11_BYTES = MAP_11_STRIDE * MAP_11_ROWS * TILE_BYTES


def parse_tile(data, x, z):
    """Validate one source MapTileModel and return active face metadata."""
    if len(data) != MAP_11_BYTES:
        raise ValueError(f"expected {MAP_11_BYTES} unpacked map-11 model bytes")
    if not (0 <= x < MAP_11_STRIDE and 0 <= z < MAP_11_ROWS):
        raise ValueError("tile coordinates outside stored map dimensions")
    base = (z * MAP_11_STRIDE + x) * TILE_BYTES
    face_count = data[base + TILE_BYTES - 2]
    height = data[base + TILE_BYTES - 1]
    if face_count > FACE_COUNT:
        raise ValueError(f"tile ({x},{z}) has impossible faceCt={face_count}")

    vertices = [
        list(struct.unpack_from("<hhhh", data, base + 8 * i)[:3])
        for i in range(VERTEX_COUNT)
    ]
    faces = []
    for idx in range(face_count):
        gfx = struct.unpack_from("<h", data, base + VERTICES_BYTES + 2 * idx)[0]
        face_start = base + VERTICES_BYTES + GFX_BYTES + idx * 4
        vertex_indexes = list(data[face_start:face_start + 4])
        if any(v >= VERTEX_COUNT for v in vertex_indexes):
            raise ValueError(
                f"tile ({x},{z}) face {idx} references vertex outside 0..21"
            )
        shade = data[base + VERTICES_BYTES + GFX_BYTES + FACE_BYTES + idx]
        faces.append({
            "face": idx,
            "local_gfx_slot": gfx,
            "uv_slot_in_land_dt": gfx if 0 <= gfx < SLOT_COUNT else None,
            "vertex_indices": vertex_indexes,
            "vertex_xyz": [vertices[v] for v in vertex_indexes],
            "shade_index": shade,
            "textured": gfx != 0,
        })
    return {
        "stored_x": x,
        "stored_z": z,
        "within_active_width": x < MAP_11_ACTIVE_WIDTH,
        "tile_height": height,
        "face_count": face_count,
        "faces": faces,
    }


def attach_land_uv_faces(tile, land, map_number=11):
    """Add each modeled face's authored UV/CLUT mapping, without guessing TPAGE."""
    if len(land) != LAND_BYTES or not (0 <= map_number < MAP_COUNT):
        raise ValueError("invalid LAND_DT size/map selection")
    record = map_number * MAP_RECORD_BYTES
    enriched = []
    for face in tile["faces"]:
        info = dict(face)
        slot = info["uv_slot_in_land_dt"]
        if slot is not None and slot != 0:
            uv_offset = record + slot * 4
            clut_offset = record + 4 * SLOT_COUNT + slot
            info["uvwh"] = list(land[uv_offset:uv_offset + 4])
            info["clut_selector"] = land[clut_offset]
            info["local_clut_row"] = (
                info["clut_selector"] - 32 if
                32 <= info["clut_selector"] <= 47 else None
            )
            # Other CLUT IDs may require external palette resources.
            info["fully_mapped_by_local_land_palette"] = (
                info["local_clut_row"] is not None
            )
        enriched.append(info)
    return dict(tile, faces=enriched)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("unpacked_models", type=Path,
                   help="EXACTLY 28x12 MapTileModel records; NOT compressed PRS")
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--z", type=int, required=True)
    p.add_argument("--land", type=Path, help="optional original LAND_DT.DAT")
    args = p.parse_args(argv)
    if args.unpacked_models.stat().st_size != MAP_11_BYTES:
        p.error(f"expected exactly {MAP_11_BYTES} unpacked map model bytes; "
                "M_MAP02.PRS must be decompressed separately")
    data = args.unpacked_models.read_bytes()
    try:
        result = parse_tile(data, args.x, args.z)
        if args.land:
            if args.land.stat().st_size != LAND_BYTES:
                p.error("wrong LAND_DT length")
            result = attach_land_uv_faces(result, args.land.read_bytes())
    except ValueError as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
