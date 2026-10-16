#!/usr/bin/env python3
"""Pin MAP02 normal-terrain projection, culling and OT submission order.

Read-only static source audit of the public pinned PC port. Not evidence
of real MAP02 pixels or actual PS1 GTE hardware behavior.
"""
import argparse
import json
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_direction_source import (
    PINNED_GRAPHICS_BLOB, function_body,
)

RENDER_ORDER = (
    "if (gfx != GFX_NULL) {",
    "gte_ldv3(&tileModel->vertices[pFaceVerts[0]], &tileModel->vertices[pFaceVerts[1]],",
    "gte_rtpt();",
    "gte_nclip();",
    "gte_stopz(&opz);",
    "if (opz > 0) {",
    "gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);",
    "gte_ldv0(&tileModel->vertices[pFaceVerts[3]]);",
    "gte_rtps();",
    "gte_stsxy(&poly->x2);",
    "gte_avsz4();",
    "gte_stotz(&otz);",
    "if (otz < 5) {",
    "AddPrim(ot + OT_SIZE - otz, poly);",
)

def verify_renderer(graphics_c: str) -> dict:
    body = function_body(graphics_c, "RenderMapTile")
    prev = -1
    for anchor in RENDER_ORDER:
        idx = body.find(anchor, prev + 1)
        if idx < 0:
            raise ValueError(f"normal terrain GTE/GPU order changed: {anchor}")
        prev = idx
    if body.count("gte_rtpt();") != 1 or body.count("gte_rtps();") != 1:
        raise ValueError("unexpected number of MAP02 projection commands")
    if body.count("AddPrim(ot + OT_SIZE - otz, poly);") != 1:
        raise ValueError("unexpected number of MAP02 OT submissions")
    return {
        "matches_normal_terrain_source_order": True,
        "renderer": "RenderMapTile",
        "projected_face_vertex_to_ft4_corner": [0,1,3,2],
        "cull_gate": "gte_nclip MAC0 > 0 after RTPT (first 3 vertices)",
        "depth": "AVSZ4 of 4 transformed SZ, then max(5, OTZ)",
        "ot_slot_expression": "OT_SIZE - otz",
        "original_renderer_checks_ot_upper_bound": False,
        "ps1_hardware_projection_verified": False,
    }

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphics_c",type=Path)
    parser.add_argument("--allow-modified-source",action="store_true")
    args=parser.parse_args()
    try:
        raw=args.graphics_c.read_bytes()
        sha=git_blob_sha1(raw)
        if sha!=PINNED_GRAPHICS_BLOB and not args.allow_modified_source:
            raise ValueError("graphics.c differs from pinned public Git blob")
        report=verify_renderer(raw.decode("utf-8"))
        report["matches_pinned_graphics"]=sha==PINNED_GRAPHICS_BLOB
        report["source_git_blob_sha1"]=sha
    except (OSError,UnicodeError,ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
