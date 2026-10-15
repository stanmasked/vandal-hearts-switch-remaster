#!/usr/bin/env python3
"""Audit which map02 source resource the pinned US PC-port selects.

Static source evidence only. Does not run the game or prove rendered pixels.
"""
import argparse
import json
import re
from pathlib import Path

from tools.prepare_map02_pcport import PINNED_BLOB_SHA1, PINNED_UPSTREAM_REF, git_blob_sha1

EXPECTED_DIMENSIONS = {
    "gMapDataSizeX": 28, "gMapDataSizeZ": 12,
    "gMapSizeX": 24, "gMapSizeZ": 12,
    "gMapMinX": 0, "gMapMaxX": 23,
    "gMapMinZ": 0, "gMapMaxZ": 11,
}
TARGETS = ((8, 19, 0), (11, 11, 0))
SOURCE_PATH = "src/states/game_setup.c"


def audit_loader_source(source: str) -> dict:
    """Fail closed if the pinned upstream structure or map-11 route changes."""
    entry = "void LoadMap(void) {"
    exit_marker = "\nvoid SetupField(void) {"
    if source.count(entry) != 1 or source.count(exit_marker) != 1:
        raise ValueError("expected exactly one LoadMap / SetupField implementation")
    begin = source.index(entry)
    end = source.index(exit_marker)
    if end <= begin:
        raise ValueError("unexpected LoadMap / SetupField order")
    body = source[begin:end]
    cases = re.findall(r"(?ms)^   case 11:\n(.*?)^      break;", body)
    if len(cases) != 1:
        raise ValueError("expected exactly one terminating LoadMap case 11")
    branch = cases[0]
    selected = re.findall(r"LoadCdFile\(\s*(CDF_[A-Z0-9_]+)\s*,\s*(\d+)\s*\);", branch)
    if selected != [("CDF_M_MAP02_PRS", "1")]:
        raise ValueError(f"map 11 must load only CDF_M_MAP02_PRS (got {selected})")

    values = {}
    for symbol, expected in EXPECTED_DIMENSIONS.items():
        assignments = re.findall(rf"\b{symbol}\s*=\s*(\d+)\s*;", branch)
        if len(assignments) != 1 or int(assignments[0]) != expected:
            raise ValueError(f"map 11 unexpected {symbol}: {assignments}; expected {expected}")
        values[symbol] = int(assignments[0])

    row_anchor = "gMapRowPointers[i] = ((MapTileModel(*)[28])gMapDataPtr)[i];"
    decode = "ProcessMapFileData(&gScratch1_801317c0[0]);"
    global_gfx = "pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;"
    base = "pTiles = (MapTileModel(*)[28])gMapDataPtr;"
    if body.count(row_anchor) != 1:
        raise ValueError("map row pointers are not initialized from 28-wide map data")
    if body.count(decode) != 1 or body.count(global_gfx) != 1 or body.count(base) != 1:
        raise ValueError("map data decode / global GFX conversion path changed")
    if not (body.index(row_anchor) < body.index("switch (gState.mapNum)") <
            body.index("   case 11:") < body.index(decode) <
            body.index(base) < body.index(global_gfx) < body.index("   SetupField();")):
        raise ValueError("map-11 selection, decompression or GFX conversion order changed")
    if not all(0 <= x <= values["gMapMaxX"] and 0 <= z <= values["gMapMaxZ"]
               for z, x, face in TARGETS if face == 0):
        raise ValueError("target faces do not fit within the map's active dimensions")
    return {
        "upstream_reference": PINNED_UPSTREAM_REF,
        "runtime_map_number": 11,
        "load_resource": selected[0][0],
        "selection": "PRS",
        "map_dimensions": values,
        "target_faces": [{"z": z, "x": x, "face": face} for z, x, face in TARGETS],
        "data_row_stride": 28,
        "gfx_conversion": "nonzero local GFX + GFX_MAP_TEXTURES_OFS",
        "evidence_scope": "pinned PC-port source path only; not runtime pixels or game-disc integrity",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_setup_c", type=Path, help="pinned US upstream src/states/game_setup.c")
    parser.add_argument("--allow-modified-source", action="store_true",
                        help="accept altered C content, explicitly tagged as noncanonical")
    args = parser.parse_args()
    try:
        data = args.game_setup_c.read_bytes()
        blob = git_blob_sha1(data)
        matches = blob == PINNED_BLOB_SHA1[SOURCE_PATH]
        if not matches and not args.allow_modified_source:
            raise ValueError("source differs from pinned upstream; use --allow-modified-source")
        report = audit_loader_source(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    report["git_blob_sha1"] = blob
    report["matches_pinned"] = matches
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
