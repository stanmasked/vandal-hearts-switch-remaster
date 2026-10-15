#!/usr/bin/env python3
"""Stage ONLY owner-provided, validated, UNPACKED map-11 geometry on SD.

This utility is separate from the two texture-bank files. It never
uploads game data or makes changes to the source tree.
"""
import argparse
import hashlib
import json
from pathlib import Path

from decode_vh_map_prs import MAX_COMPRESSED_BYTES, decode_map_prs
from inspect_vh_map_geometry import (
    FACE_COUNT, GFX_BYTES, MAP_11_BYTES, MAP_11_ROWS, MAP_11_STRIDE,
    TILE_BYTES, VERTICES_BYTES,
)
from stage_vh_private_map_bank import RELATIVE_DESTINATION

GEOMETRY_NAME = "MAP11_MODELS_28X12.BIN"
GEOMETRY_MANIFEST = "geometry-manifest.json"


def validate_map11_models(data):
    """Reject malformed tile and vertex topology before creating SD files."""
    if len(data) != MAP_11_BYTES:
        raise ValueError(f"expected {MAP_11_BYTES} bytes of unpacked MapTileModel")
    populated = 0
    faces = 0
    for i in range(MAP_11_STRIDE * MAP_11_ROWS):
        offset = i * TILE_BYTES
        count = data[offset + TILE_BYTES - 2]
        if count > FACE_COUNT:
            raise ValueError(f"tile #{i} has invalid faceCt {count}")
        if count:
            populated += 1
        faces += count
        for k in range(count):
            start = offset + VERTICES_BYTES + GFX_BYTES + k * 4
            if any(n >= 22 for n in data[start:start + 4]):
                raise ValueError(f"tile #{i} face {k} references invalid vertex")
    return {"tile_records": MAP_11_STRIDE * MAP_11_ROWS,
            "populated_tiles": populated, "active_faces": faces}


def stage_map11_geometry(unpacked, sd_root):
    stats = validate_map11_models(unpacked)
    destination = Path(sd_root) / RELATIVE_DESTINATION
    path = destination / GEOMETRY_NAME
    manifest = destination / GEOMETRY_MANIFEST
    if path.exists() or path.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise FileExistsError("private map geometry exists; refusing to overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    metadata = {
        "source": "user-provided unpacked map-11 tile models",
        "geometry_sha256": hashlib.sha256(unpacked).hexdigest(),
        "model_bytes": MAP_11_BYTES,
        "map_number": 11, **stats,
    }
    path.write_bytes(unpacked)
    manifest.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return metadata


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prs", type=Path, help="local compressed M_MAP02.PRS")
    modes.add_argument("--unpacked", type=Path, help="local 102144-byte map model prefix")
    p.add_argument("--sd-root", type=Path, required=True,
                   help="mountpoint of the user's Switch SD card")
    args = p.parse_args(argv)
    try:
        if args.prs:
            if args.prs.stat().st_size > MAX_COMPRESSED_BYTES + 4:
                p.error("PRS input exceeds bounded maximum")
            unpacked = decode_map_prs(args.prs.read_bytes(), min_output=MAP_11_BYTES)
            unpacked = unpacked[:MAP_11_BYTES]
        else:
            if args.unpacked.stat().st_size != MAP_11_BYTES:
                p.error("unpacked tile slab must be exactly 102144 bytes")
            unpacked = args.unpacked.read_bytes()
        result = stage_map11_geometry(unpacked, args.sd_root)
    except (ValueError, FileExistsError, OSError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
