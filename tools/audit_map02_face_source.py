#!/usr/bin/env python3
"""Fail-closed verification of MAP02 face-model and GPU UV corner semantics.

Audits the pinned upstream files, not rendered gameplay. No original game
assets or screenshot assumptions are involved.
"""
import argparse
import json
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1

BLOBS = {
    "include/field.h": "4fda8fb03c7d13d7e0e5157bae2c705185ba001b",
    "src/core/graphics.c": "b89a83c226639f6b4db13ddbf0e3118b49262d39",
    "platform/pc/include/PsyQ/libgpu.h": "1e8339397b4f01304c10caf6e8ea28968448a8f2",
}
RENDERERS = (
    ("RenderMapTile", "RenderEdgeMapTile"),
    ("RenderEdgeMapTile", "RenderOverheadMapTile"),
    ("RenderOverheadMapTile", "GetBestViewOfTarget"),
)

FIELD_LAYOUT = (
    "typedef struct MapTileModel {\n"
    "   SVECTOR vertices[22];\n"
    "   s16 gfx[18];\n"
    "   u8 faces[18][4];\n"
    "   u8 shades[18]; // TBD\n"
    "   u8 faceCt;\n"
    "   u8 height;\n"
    "} MapTileModel;"
)

UV_MACRO = (
    "#define setUVWH(p, _u0, _v0, _w, _h) \\\n"
    "    ((p)->u0 = (_u0), (p)->v0 = (_v0), \\\n"
    "     (p)->u1 = (_u0) + (_w), (p)->v1 = (_v0), \\\n"
    "     (p)->u2 = (_u0), (p)->v2 = (_v0) + (_h), \\\n"
    "     (p)->u3 = (_u0) + (_w), (p)->v3 = (_v0) + (_h))"
)

RENDERER_ANCHORS = (
    "pFaceVerts = &tileModel->faces[faceIdx][0];",
    "gte_ldv3(&tileModel->vertices[pFaceVerts[0]], &tileModel->vertices[pFaceVerts[1]],",
    "&tileModel->vertices[pFaceVerts[2]]);",
    "gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);",
    "gte_ldv0(&tileModel->vertices[pFaceVerts[3]]);",
    "gte_stsxy(&poly->x2);",
    "AddPrim(ot + OT_SIZE - otz, poly);",
)


def verify_source_contract(field: str, graphics: str, gpu: str) -> dict:
    if field.count(FIELD_LAYOUT) != 1:
        raise ValueError("MapTileModel data structure and 304-byte layout changed")
    if gpu.count(UV_MACRO) != 1:
        raise ValueError("setUVWH PS1 UV coordinate convention changed")
    paths = []
    # Fail on an absent/duplicated function before deriving neighbor
    # boundaries. This distinguishes missing render paths from malformed code.
    for name, _ in RENDERERS:
        if graphics.count(f"void {name}(") != 1:
            raise ValueError(f"{name} function missing or ambiguous")
    for name, next_name in RENDERERS:
        anchor = f"void {name}("
        first = graphics.index(anchor)
        last = graphics.find(f"{next_name}(", first + len(anchor))
        if last < first:
            raise ValueError(f"{name} function boundary changed")
        body = graphics[first:last]
        for statement in RENDERER_ANCHORS:
            if statement not in body:
                raise ValueError(f"{name} GPU face mapping changed: {statement}")
        if name != "RenderOverheadMapTile":
            if "setUVWH(poly, texX, texY, texW, texH);" not in body:
                raise ValueError(f"{name} no longer samples GFX UVWH normally")
        elif ("setUVWH(poly, gGfxSubTextures[gfx][0], gGfxSubTextures[gfx][1],"
              not in body):
            raise ValueError("overhead GFX UVWH mapping changed")
        paths.append(name)
    return {
        "source_layout": {
            "tile_bytes": 304,
            "vertices": 22,
            "vertex_bytes": 8,
            "gfx_offset": 176,
            "gfx_type": "s16",
            "faces_offset": 212,
            "shades_offset": 284,
            "face_count_offset": 302,
            "height_offset": 303,
        },
        "renderer_paths": paths,
        "source_face_perimeter_to_polygon_vertices": [0, 1, 3, 2],
        "source_face_perimeter_to_uv": ["uv0", "uv1", "uv3", "uv2"],
        "field_and_gpu_layout_verified": True,
        "scope": "pinned C source interpretation, not runtime projection or visible pixels",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream_root", type=Path)
    parser.add_argument("--allow-modified-source", action="store_true")
    args = parser.parse_args()
    try:
        data = {p: (args.upstream_root / p).read_bytes() for p in BLOBS}
        identities = {p: git_blob_sha1(b) for p, b in data.items()}
        matches = all(identities[p] == BLOBS[p] for p in BLOBS)
        if not matches and not args.allow_modified_source:
            raise ValueError("upstream face/renderer/GPU source blobs differ from pinned version")
        result = verify_source_contract(
            *(data[p].decode("utf-8") for p in BLOBS)
        )
        result["matches_pinned_source"] = matches
        result["source_git_blob_sha1"] = identities
    except (OSError, ValueError, UnicodeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
