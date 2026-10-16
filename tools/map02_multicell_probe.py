#!/usr/bin/env python3
"""Explicit multi-tile MAP02 face-0 placement probe.

Tile-local geometry is decoded from source records. Grid-to-world spacing and
axis orientation are *inputs*, not asserted facts about the original engine.
No GTE camera, projection, OTZ, lighting, clipping or pixels are emulated here.
"""
from __future__ import annotations

from tools.map02_face_geometry import decode_face_0


def place_faces(decoded: bytes, cells, uvwh, *, step_x: int, step_z: int):
    """Return a set of translated faces with unambiguous grid coordinates.

    cells: iterable of (z,x), uvwh: mapping keyed by (z,x).
    Translation is (x*step_x, 0, z*step_z). Keep signed steps to test
    reverse grid directions. Duplicate or missing cells are rejected.
    """
    if type(step_x) is not int or type(step_z) is not int or not step_x or not step_z:
        raise ValueError("nonzero integer grid steps required")
    output = []
    seen = set()
    for z, x in cells:
        key = (z, x)
        if key in seen:
            raise ValueError("duplicate map cell")
        seen.add(key)
        face = decode_face_0(decoded, z, x, uvwh[key])
        vertices = [c["model_xyz"] for c in face["face_corners"]]
        output.append({
            "z": z, "x": x, "record_index": face["record_index"],
            "grid_offset_xyz": [x * step_x, 0, z * step_z],
            "world_xyz_hypothesis": [
                [p[0] + x * step_x, p[1], p[2] + z * step_z]
                for p in vertices
            ],
            "source_face": face,
        })
    return output


def shared_vertices(first: dict, second: dict):
    """Report exactly overlapping translated corners (without adjacency claims)."""
    a = {tuple(p) for p in first["world_xyz_hypothesis"]}
    b = {tuple(p) for p in second["world_xyz_hypothesis"]}
    return [list(p) for p in sorted(a & b)]
