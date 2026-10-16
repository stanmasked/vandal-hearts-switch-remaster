#!/usr/bin/env python3
"""Compare the 26 C direction vectors with pinned PC-port SetupLightNormals.

Also checks that UpdateMapTileLighting continues to choose three source
vertices, cross-product them, search all 26 dot products and apply the
original tie-break before writing a face's shade index.

This is a source-level consistency audit; it does NOT prove that the
portable classifier rounds exactly like the hardware GTE.
"""
import argparse
import json
import re
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1

PINNED_GRAPHICS_BLOB = "b89a83c226639f6b4db13ddbf0e3118b49262d39"
DIRECTIONS = (
    (0,1,0), (0,-1,0), (1,0,0), (0,0,1), (-1,0,0), (0,0,-1),
    (1,0,-1), (1,0,1), (-1,0,1), (-1,0,-1),
    (1,1,0), (0,1,1), (-1,1,0), (0,1,-1),
    (1,1,-1), (1,1,1), (-1,1,1), (-1,1,-1),
    (1,-1,0), (0,-1,1), (-1,-1,0), (0,-1,-1),
    (1,-1,-1), (1,-1,1), (-1,-1,1), (-1,-1,-1),
)
ASSIGN = re.compile(r"v\[(\d+)\]\.(vx|vy|vz)\s*=\s*(-?\d+)\s*;")
HEADER = re.compile(
    r"static const VhMap02Direction vh_map02_directions\[26\] = \{(.*?)\};",
    re.S
)
COORD = re.compile(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\}")
FACE_ANCHORS = (
    "var_a1 = tileModel->faces[i][0];",
    "var_a0 = tileModel->faces[i][1];",
    "var_t0 = tileModel->faces[i][2];",
    "var_a2 = tileModel->faces[i][3];",
    "if (var_a1 == var_a0)",
    "} else if (var_a1 == var_t0)",
    "} else if (var_a1 == var_a2)",
    "} else if (var_a0 == var_t0)",
    "gte_OuterProduct0(&vec_sp20, &vec_sp30, &vec_sp10);",
    "VectorNormalS(&vec_sp10, &svec_sp40);",
    "greatest = -0x1000000;",
    "for (j = 0; j < 26; j++)",
    "if (iVar6 > greatest)",
    "} else if (iVar6 == greatest)",
    "if (ct1 > ct2)",
    "tileModel->shades[i] = iVar5;",
)


def function_body(source: str, name: str) -> str:
    head = f"void {name}("
    if source.count(head) != 1:
        raise ValueError(f"{name} must occur exactly once")
    start = source.index(head)
    end = source.find("\nvoid ", start + len(head))
    if end < 0:
        raise ValueError(f"{name} has no verifiable following function boundary")
    return source[start:end]


def verify_directions(graphics: str, portable_header: str) -> dict:
    setup = function_body(graphics, "SetupLightNormals")
    found = ASSIGN.findall(setup)
    if len(found) != 78:
        raise ValueError(f"expected 78 source direction assignments, found {len(found)}")
    entries = {}
    for index, axis, val in found:
        key = (int(index), axis)
        if key in entries:
            raise ValueError(f"duplicate source assignment {key}")
        entries[key] = int(val)
    restored = tuple(
        tuple(entries.get((i, axis)) for axis in ("vx", "vy", "vz"))
        for i in range(26)
    )
    if restored != DIRECTIONS:
        raise ValueError("original 26 direction vectors changed")
    if "VectorNormalS(&v[i], &gSideLightNormals[i]);" not in setup:
        raise ValueError("source direction normalization call changed")
    if not ("for (i = 0; i < ARRAY_COUNT(v); i++)" in setup):
        raise ValueError("source direction count loop changed")

    match = HEADER.search(portable_header)
    if not match or len(HEADER.findall(portable_header)) != 1:
        raise ValueError("portable 26-direction array missing or ambiguous")
    c_values = tuple(tuple(map(int, item)) for item in COORD.findall(match.group(1)))
    if c_values != DIRECTIONS:
        raise ValueError("portable direction array differs from pinned source")

    body = function_body(graphics, "UpdateMapTileLighting")
    for statement in FACE_ANCHORS:
        if statement not in body:
            raise ValueError(f"original face-normal selection changed: {statement}")
    for axis in ("vx", "vy", "vz"):
        if f"gSideLightNormals[j].{axis} * svec_sp40.{axis}" not in body:
            raise ValueError(f"source dot product missing {axis} axis")

    return {
        "direction_count": len(DIRECTIONS),
        "source_component_assignments": len(found),
        "portable_direction_table_matches_upstream": True,
        "source_vectornormal_binding": True,
        "source_face_cross_product_and_tiebreak": True,
        "rounding_equivalence_with_gte": False,
        "scope": "pinned C source static audit; no game data, no GTE roundoff verification",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graphics_c", type=Path)
    parser.add_argument("portable_header", type=Path)
    parser.add_argument("--allow-modified-source", action="store_true")
    args = parser.parse_args()
    try:
        raw = args.graphics_c.read_bytes()
        sha = git_blob_sha1(raw)
        if sha != PINNED_GRAPHICS_BLOB and not args.allow_modified_source:
            raise ValueError("graphics.c differs from pinned US PC-port Git blob")
        result = verify_directions(raw.decode("utf-8"),
                                   args.portable_header.read_text(encoding="utf-8"))
        result["matches_pinned_source"] = sha == PINNED_GRAPHICS_BLOB
        result["source_git_blob_sha1"] = sha
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
