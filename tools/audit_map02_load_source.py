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
CD_SOURCE_PATH = "src/core/cd.c"
CD_HEADER_PATH = "include/cd_files.h"
PINNED_CD_BLOBS = {
    CD_SOURCE_PATH: "30d43504c8becadaca4c475abce9d40b0bc9dc2b",
    CD_HEADER_PATH: "cea949e05ad4d914732f1a96a1faed1329a56b6b",
}



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



def audit_cd_route(cd_source: str, cd_header: str) -> dict:
    """Verify the map02 PRS index, source sector table and CD loader bindings."""
    entry = re.findall(r"(?m)^\s*CDF_M_MAP02_PRS\s*=\s*(\d+)\s*,",
                       cd_header)
    if entry != ["151"]:
        raise ValueError(f"unexpected CDF_M_MAP02_PRS enum identifier: {entry}")
    row = re.findall(
        r"(?m)^\s*\[CDF_M_MAP02_PRS\]\s*=\s*\{\s*"
        r"(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*"
        r"(gScratch1_801317c0)\s*\},",
        cd_source,
    )
    if len(row) != 1:
        raise ValueError("expected exactly one PRS mapping to scratch1 in gCdFiles")
    start, count, destination = row[0]
    if (int(start, 16), int(count, 16)) != (0x1BCC, 0x0C):
        raise ValueError(f"unexpected map02 PRS sector table: {start}, {count}")
    if cd_source.count("CdFileInfo gCdFiles[712]") != 1:
        raise ValueError("pinned gCdFiles table declaration changed")
    loader = cd_source.find("void LoadCdFile(s32 cdfIdx, s32 showLoadingScreen) {")
    if loader < 0:
        raise ValueError("LoadCdFile entry point changed")
    loads = (
        "gCdLoader.cdf = cdfIdx;",
        "gCdLoader.sectorsToRead = gCdFiles[cdfIdx].sectorCt;",
        "gCdLoader.sector = gCdFiles[cdfIdx].startingSector;",
    )
    if not all(cd_source.find(statement, loader, loader + 1200) >= 0 for statement in loads):
        raise ValueError("LoadCdFile does not initialize sector read from gCdFiles table")
    return {
        "cd_file_enum": 151,
        "cd_table_start_sector": int(start, 16),
        "cd_table_sector_count": int(count, 16),
        "cd_destination": destination,
        "cd_evidence_scope": "US pinned source CD table only; not verified against any user's disc image",
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game_setup_c", type=Path, help="pinned US upstream src/states/game_setup.c")
    parser.add_argument("--allow-modified-source", action="store_true",
                        help="accept altered C content, explicitly tagged as noncanonical")
    parser.add_argument("--cd-source", type=Path,
                        help="pinned upstream src/core/cd.c; requires --cd-header")
    parser.add_argument("--cd-header", type=Path,
                        help="pinned upstream include/cd_files.h; requires --cd-source")
    args = parser.parse_args()
    if (args.cd_source is None) != (args.cd_header is None):
        parser.error("--cd-source and --cd-header must be supplied together")
    try:
        data = args.game_setup_c.read_bytes()
        blob = git_blob_sha1(data)
        matches = blob == PINNED_BLOB_SHA1[SOURCE_PATH]
        if not matches and not args.allow_modified_source:
            raise ValueError("source differs from pinned upstream; use --allow-modified-source")
        report = audit_loader_source(data.decode("utf-8"))
        if args.cd_source is not None:
            cd_data = args.cd_source.read_bytes()
            header_data = args.cd_header.read_bytes()
            cd_blob = git_blob_sha1(cd_data)
            header_blob = git_blob_sha1(header_data)
            cd_ok = cd_blob == PINNED_CD_BLOBS[CD_SOURCE_PATH]
            header_ok = header_blob == PINNED_CD_BLOBS[CD_HEADER_PATH]
            if not (cd_ok and header_ok) and not args.allow_modified_source:
                raise ValueError("CD source/header differ from pinned US upstream")
            report.update(audit_cd_route(cd_data.decode("utf-8"),
                                         header_data.decode("utf-8")))
            report["cd_source_git_blob_sha1"] = cd_blob
            report["cd_header_git_blob_sha1"] = header_blob
            report["cd_sources_match_pinned"] = cd_ok and header_ok
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
    report["git_blob_sha1"] = blob
    report["matches_pinned"] = matches
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
