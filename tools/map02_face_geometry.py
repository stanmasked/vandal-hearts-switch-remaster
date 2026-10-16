#!/usr/bin/env python3
"""Map02 target-face source geometry and POLY_FT4 UV wiring (read-only).

Structure verified against pinned US PC-port include/field.h:
SVECTOR vertices[22] (8-byte); s16 gfx[18]; u8 faces[18][4];
u8 shades[18]; u8 faceCt; u8 height; total 304 bytes.

src/core/graphics.c projects face vertices [0,1,2] into POLY_FT4
corners [0,1,3], then face vertex [3] into poly corner [2].
platform/pc/include/PsyQ/libgpu.h setUVWH assigns UV corners [0,1,2,3].
Therefore the ordered source face perimeter maps to UV
[(u,v),(u+w,v),(u+w,v+h),(u,v+h)].

This is source-local quad geometry, not camera projection or evidence
that the GPU eventually displayed it.
"""
from __future__ import annotations

import hashlib
import struct

STRIDE = 28
RECORD_SIZE = 304
RECORD_COUNT = STRIDE * 22
ACTIVE_WIDTH = 24
ACTIVE_HEIGHT = 12
VERTEX_COUNT = 22
FACE_COUNT_MAX = 18
VERTEX_BYTES = 8
GFX_OFFSET = 176
FACE_TABLE_OFFSET = 212
SHADE_TABLE_OFFSET = 284
FACE_COUNT_OFFSET = 302
HEIGHT_OFFSET = 303

# GPU FT4 memory structure is a triangle-strip arrangement. The source
# face's cyclic perimeter order [a,b,c,d] becomes poly x0=a, x1=b,
# x3=c, x2=d. UV0/1/3/2 respectively follow that same cyclic perimeter.
POLYGON_CORNER_SEQUENCE = ("uv0_poly0", "uv1_poly1", "uv3_poly3", "uv2_poly2")


def tile_record(decoded: bytes, z: int, x: int) -> bytes:
    if type(z) is not int or type(x) is not int or not (
        0 <= z < ACTIVE_HEIGHT and 0 <= x < ACTIVE_WIDTH
    ):
        raise ValueError(f"target tile outside active 24x12 map: z={z} x={x}")
    if len(decoded) < RECORD_COUNT * RECORD_SIZE:
        raise ValueError("decoded map is shorter than 616 complete tile records")
    start = (z * STRIDE + x) * RECORD_SIZE
    return decoded[start:start + RECORD_SIZE]


def decode_face(decoded: bytes, z: int, x: int, face_index: int,
                uvwh: tuple[int, int, int, int]) -> dict:
    """Extract a chosen face with original table offsets and FT4 UV mapping."""
    record = tile_record(decoded, z, x)
    face_count = record[FACE_COUNT_OFFSET]
    if face_count < 1 or face_count > FACE_COUNT_MAX:
        raise ValueError(f"z={z},x={x}: faceCt={face_count}, expected 1..18")
    if type(face_index) is not int or not 0 <= face_index < face_count:
        raise ValueError(f"z={z},x={x}: face index outside 0..{face_count - 1}")
    indices = tuple(record[FACE_TABLE_OFFSET + face_index * 4:
                           FACE_TABLE_OFFSET + (face_index + 1) * 4])
    if any(vertex >= VERTEX_COUNT for vertex in indices):
        raise ValueError(f"z={z},x={x}: face-{face_index} vertex index outside 0..21")
    if len(set(indices)) < 3:
        raise ValueError(f"z={z},x={x}: degenerate face-{face_index} vertex indices")
    coords = [
        list(struct.unpack_from("<hhh", record, index * VERTEX_BYTES))
        for index in indices
    ]
    if len(uvwh) != 4 or any(type(component) is not int for component in uvwh):
        raise ValueError("UVWH must be exactly four integer values")
    u, v, w, h = uvwh
    if not (0 <= u <= 255 and 0 <= v <= 255 and 0 < w <= 255 - u
            and 0 < h <= 255 - v):
        raise ValueError(f"invalid tile-face UVWH {uvwh}")
    uv = ((u, v), (u + w, v), (u + w, v + h), (u, v + h))
    a = [coords[1][k] - coords[0][k] for k in range(3)]
    b = [coords[2][k] - coords[0][k] for k in range(3)]
    cross = (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )
    corners = [
        {
            "face_index": i,
            "model_vertex_index": indices[i],
            "model_xyz": coords[i],
            "gpu_corner": POLYGON_CORNER_SEQUENCE[i],
            "uv": list(uv[i]),
        }
        for i in range(4)
    ]
    return {
        "z": z, "x": x, "face": face_index,
        "record_index": z * STRIDE + x,
        "local_gfx": struct.unpack_from("<h", record, GFX_OFFSET + face_index * 2)[0],
        "face_count": face_count,
        "face_shade": record[SHADE_TABLE_OFFSET + face_index],
        "tile_height": record[HEIGHT_OFFSET],
        "face_vertex_indices": list(indices),
        "face_corners": corners,
        "first_triangle_cross_xyz": list(cross),
        "first_triangle_nonzero_area": any(cross),
        "perimeter_vertex_order": "0,1,2,3",
        "gpu_poly_vertex_assignments": ["x0=face[0]", "x1=face[1]",
                                        "x3=face[2]", "x2=face[3]"],
        "uv_assignment": "setUVWH: uv0=(u,v),uv1=(u+w,v),uv2=(u,v+h),uv3=(u+w,v+h)",
        "geometry_scope": "source-local vertices and UV; no camera or pixels rendered",
    }


def decode_face_0(decoded: bytes, z: int, x: int,
                  uvwh: tuple[int, int, int, int]) -> dict:
    """Backward-compatible first-face decoder."""
    return decode_face(decoded, z, x, 0, uvwh)


def compare_face_geometry(prs: bytes, dat: bytes, z: int, x: int,
                          prs_uvwh: tuple[int, int, int, int],
                          dat_uvwh: tuple[int, int, int, int]) -> dict:
    """Compare local polygon shape while preserving GFX and UV distinctions."""
    p_record = tile_record(prs, z, x)
    d_record = tile_record(dat, z, x)
    p = decode_face_0(prs, z, x, prs_uvwh)
    d = decode_face_0(dat, z, x, dat_uvwh)
    # Remove just the 16-bit face-0 material index. A changed shade,
    # vertex or other face index must not silently pass.
    p_nonmaterial = p_record[:GFX_OFFSET] + p_record[GFX_OFFSET + 2:]
    d_nonmaterial = d_record[:GFX_OFFSET] + d_record[GFX_OFFSET + 2:]
    shape_matches = p_nonmaterial == d_nonmaterial
    return {
        "z": z, "x": x, "face": 0,
        "shape_and_other_tile_data_identical": shape_matches,
        "prs_face": p,
        "dat_face": d,
        "prs_tile_except_face_gfx_sha256": hashlib.sha256(p_nonmaterial).hexdigest(),
        "dat_tile_except_face_gfx_sha256": hashlib.sha256(d_nonmaterial).hexdigest(),
        "model_vertex_positions_identical": [
            corner["model_xyz"] for corner in p["face_corners"]
        ] == [corner["model_xyz"] for corner in d["face_corners"]],
        "uv_corner_positions_identical": [
            corner["uv"] for corner in p["face_corners"]
        ] == [corner["uv"] for corner in d["face_corners"]],
        "evidence_scope": "model-space quad and UV corners, not PS1 rasterized pixels",
    }
