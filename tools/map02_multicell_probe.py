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


def shared_edges(first: dict, second: dict):
    """Find identical complete 3D boundary segments, independent of winding.

    A shared point alone does not establish an edge; differing heights
    intentionally do not match. This is exact integer model-space geometry,
    not a screen-space seam or PS1 rasterization test.
    """
    def segments(face):
        vertices = [tuple(p) for p in face["world_xyz_hypothesis"]]
        return {
            tuple(sorted((vertices[i], vertices[(i + 1) % len(vertices)])))
            for i in range(len(vertices))
            if vertices[i] != vertices[(i + 1) % len(vertices)]
        }

    common = segments(first) & segments(second)
    return [[list(a), list(b)] for a, b in sorted(common)]


def boundary_report(faces):
    """Classify each translated perimeter segment by incidence count.

    Counts >2 identify non-manifold or overlapping synthetic placements.
    Height differences remain separate edges rather than being merged.
    """
    incidence = {}
    for face in faces:
        vertices = [tuple(p) for p in face["world_xyz_hypothesis"]]
        for i in range(len(vertices)):
            a, b = vertices[i], vertices[(i + 1) % len(vertices)]
            if a == b:
                continue
            segment = tuple(sorted((a, b)))
            incidence.setdefault(segment, []).append((face["z"], face["x"]))
    return {
        "outer_edges": sum(len(owners) == 1 for owners in incidence.values()),
        "paired_edges": sum(len(owners) == 2 for owners in incidence.values()),
        "nonmanifold_edges": sum(len(owners) > 2 for owners in incidence.values()),
        "edge_count": len(incidence),
    }


def face_cross_xyz(vertices):
    """First-triangle cross product using exact integer differences."""
    if len(vertices) != 4 or any(len(p) != 3 for p in vertices):
        raise ValueError("expected four XYZ vertices")
    a = [vertices[1][i] - vertices[0][i] for i in range(3)]
    b = [vertices[2][i] - vertices[0][i] for i in range(3)]
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def placement_invariants(face):
    """Audit translation without introducing floating-point projection.

    Cross products must be identical before and after translation, even
    when the face has zero area. Vertex order, GPU corner mapping and
    local UVs must remain attached to their source vertices.
    """
    original = face["source_face"]["face_corners"]
    offset = face["grid_offset_xyz"]
    placed = face["world_xyz_hypothesis"]
    if len(original) != 4 or len(placed) != 4 or len(offset) != 3:
        raise ValueError("invalid placed face")
    local = [corner["model_xyz"] for corner in original]
    return {
        "translation_exact": all(
            placed[i] == [local[i][axis] + offset[axis] for axis in range(3)]
            for i in range(4)
        ),
        "cross_preserved": face_cross_xyz(local) == face_cross_xyz(placed),
        "local_cross_xyz": face_cross_xyz(local),
        "placed_cross_xyz": face_cross_xyz(placed),
        "vertex_indices": [corner["model_vertex_index"] for corner in original],
        "gpu_corners": [corner["gpu_corner"] for corner in original],
        "uv_corners": [corner["uv"] for corner in original],
    }


def order_faces_by_external_otz(faces, otz_by_cell):
    """Associate caller-captured GTE OTZ with cells; never estimate depth.

    Ordering is ascending OTZ for diagnostics only, NOT a PS1 ordering-table
    insertion policy or a claim about the renderer's draw order. Equal depths
    retain input order. Every cell needs a distinct (z,x) and a supplied
    unsigned 16-bit OTZ. Booleans and extra measurements are rejected.
    """
    keys = [(face["z"], face["x"]) for face in faces]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate cell in depth batch")
    if set(otz_by_cell) != set(keys):
        raise ValueError("OTZ measurements must match placed cells exactly")
    for key in keys:
        value = otz_by_cell[key]
        if type(value) is not int or not 0 <= value <= 65535:
            raise ValueError("OTZ must be an unsigned 16-bit integer")
    return [
        {"z": face["z"], "x": face["x"],
         "record_index": face["record_index"], "otz": otz_by_cell[key],
         "input_order": i}
        for i, (key, face) in sorted(
            enumerate(zip(keys, faces)),
            key=lambda pair: (otz_by_cell[pair[1][0]], pair[0])
        )
    ]
