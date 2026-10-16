#!/usr/bin/env python3
"""Opt-in, source-pinned PC-port MAP02 GTE camera/face evidence instrumentation.

Creates two new C files; neither game resources nor original upstream source
are overwritten. Never claims that camera data was actually captured.
The real runtime emits at most one JSON event per target face when normal
RenderMapTile processes it (even if NCLIP culls the face).
"""
import argparse
from pathlib import Path

from tools.prepare_map02_pcport import git_blob_sha1
from tools.audit_map02_direction_source import (
    PINNED_GRAPHICS_BLOB, PINNED_PC_LIBGTE_BLOB,
)

GUARD = "VH_TRACE_MAP02_CAMERA"
CAMERA_COUNT = 16
LIBGTE_ANCHOR = "void PC_GteDebugState(int *ofx, int *ofy, int *h, int *rt00, int *rt02, int *rt22,"
RENDER_START = "void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {"
RENDER_END = "void RenderEdgeMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {"

LIBGTE_HOOK = r"""
#if defined(VH_TRACE_MAP02_CAMERA)
/* Exact resident GTE rotation, translation and perspective registers.
 * Camera layout: rt[0..8] row-major, tr[9..11], OFX, OFY, H, ZSF4.
 * No approximate reconstruction from the game's higher-level camera. */
void VH_Map02CameraRegisters(int values[16]) {
    int i, j;
    if (!values) return;
    for (i = 0; i < 3; ++i) {
        for (j = 0; j < 3; ++j)
            values[i * 3 + j] = g.rt.m[i][j];
        values[9 + i] = g.tr[i];
    }
    values[12] = g.ofx;
    values[13] = g.ofy;
    values[14] = g.h;
    values[15] = g.zsf4;
}
#endif
"""

GRAPHICS_HOOK = r"""
#if defined(PC_FEAT) && defined(VH_TRACE_MAP02_CAMERA)
#include <stdio.h>
extern void VH_Map02CameraRegisters(int values[16]);
static unsigned char vh_map02_camera_once[2] = {0, 0};

/* Only the two disputed normal-terrain faces, not edge/overhead passes. */
static int VH_Map02CameraTarget(const MapTileModel *tile, int face) {
   if (gState.mapNum != 11 || face != 0) return -1;
   if (tile == &gMapRowPointers[8][19]) return 0;
   if (tile == &gMapRowPointers[11][11]) return 1;
   return -1;
}
static void VH_Map02CameraEvent(const MapTileModel *tile, int target,
                                int gfx, const int registers[16],
                                int nclip, const POLY_FT4 *poly, int raw_otz) {
   int i, z, x;
   const SVECTOR *v;
   if (target < 0 || target > 1 || vh_map02_camera_once[target]) return;
   vh_map02_camera_once[target] = 1;
   z = target == 0 ? 8 : 11;
   x = target == 0 ? 19 : 11;
   printf("{\"stage\":\"camera_projection\",\"z\":%d,\"x\":%d,"
          "\"face\":0,\"path\":\"normal\",\"frame\":%u,\"gfx\":%d,"
          "\"camera\":[", z, x, (unsigned)gState.frameCounter, gfx);
   for (i = 0; i < 16; ++i)
      printf("%s%d", i ? "," : "", registers[i]);
   printf("],\"vertices\":[");
   for (i = 0; i < 4; ++i) {
      v = &tile->vertices[tile->faces[0][i]];
      printf("%s%d,%d,%d", i ? "," : "", (int)v->vx, (int)v->vy, (int)v->vz);
   }
   printf("],\"nclip\":%d,\"visible\":%s,\"screen\":",
          nclip, nclip > 0 ? "true" : "false");
   if (nclip > 0 && poly) {
      /* POLY_FT4 storage order, deliberately NOT face perimeter order. */
      printf("[%d,%d,%d,%d,%d,%d,%d,%d]",
         (int)poly->x0, (int)poly->y0,
         (int)poly->x1, (int)poly->y1,
         (int)poly->x2, (int)poly->y2,
         (int)poly->x3, (int)poly->y3);
      printf(",\"otz\":%d", raw_otz);
   } else {
      printf("null,\"otz\":null");
   }
   puts("}");
   fflush(stdout);
}
#endif
"""

PRE_RTPT = """#if defined(PC_FEAT) && defined(VH_TRACE_MAP02_CAMERA)
         int vh_camera_target = VH_Map02CameraTarget(tileModel, faceIdx);
         int vh_camera_registers[16] = {0};
         if (vh_camera_target >= 0 && !vh_map02_camera_once[vh_camera_target])
            VH_Map02CameraRegisters(vh_camera_registers);
#endif
"""
POST_NCLIP = """#if defined(PC_FEAT) && defined(VH_TRACE_MAP02_CAMERA)
         if (vh_camera_target >= 0 && opz <= 0)
            VH_Map02CameraEvent(tileModel, vh_camera_target, gfx,
                                vh_camera_registers, opz, NULL, 0);
#endif
"""
POST_AVSZ4 = """#if defined(PC_FEAT) && defined(VH_TRACE_MAP02_CAMERA)
            if (vh_camera_target >= 0)
               VH_Map02CameraEvent(tileModel, vh_camera_target, gfx,
                                   vh_camera_registers, opz, poly, otz);
#endif
"""


def replace_one(text: str, marker: str, with_text: str, context: str) -> str:
    if text.count(marker) != 1:
        raise ValueError(f"{context}: expected unique pinned anchor, got {text.count(marker)}")
    return text.replace(marker, with_text, 1)


def instrument_libgte(source: str) -> str:
    if GUARD in source:
        raise ValueError("libgte already has camera instrumentation")
    return replace_one(source, LIBGTE_ANCHOR, LIBGTE_HOOK + "\n" + LIBGTE_ANCHOR,
                       "libgte camera state accessor")


def instrument_graphics(source: str) -> str:
    if GUARD in source:
        raise ValueError("graphics already has camera instrumentation")
    if source.count(RENDER_START) != 1 or source.count(RENDER_END) != 1:
        raise ValueError("pinned RenderMapTile function boundaries changed")
    start, end = source.index(RENDER_START), source.index(RENDER_END)
    if start >= end:
        raise ValueError("RenderMapTile bounds reversed")
    body = source[start:end]
    body = replace_one(body, "         gte_rtpt();\n",
                       PRE_RTPT + "         gte_rtpt();\n", "camera before RTPT")
    body = replace_one(body, "         gte_stopz(&opz);\n",
                       "         gte_stopz(&opz);\n" + POST_NCLIP,
                       "NCLIP result before cull")
    body = replace_one(body, "            gte_stotz(&otz);\n",
                       "            gte_stotz(&otz);\n" + POST_AVSZ4,
                       "unclamped AVSZ4 OTZ")
    prefix = source[:start]
    return prefix + GRAPHICS_HOOK + "\n" + body + source[end:]


def prepare(upstream: Path, destination: Path, *, allow_modified=False) -> dict:
    files = {
        "src/core/graphics.c": (PINNED_GRAPHICS_BLOB, instrument_graphics,
                                "graphics.camera.c"),
        "platform/pc/src/libgte.c": (PINNED_PC_LIBGTE_BLOB, instrument_libgte,
                                    "libgte.camera.c"),
    }
    if destination.exists():
        raise ValueError("output directory already exists; refusing overwrite")
    staged = {}
    for path, (blob, instrumenter, name) in files.items():
        raw = (upstream / path).read_bytes()
        actual = git_blob_sha1(raw)
        if actual != blob and not allow_modified:
            raise ValueError(f"refusing changed pinned source: {path} ({actual})")
        staged[name] = instrumenter(raw.decode("utf-8"))
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in staged.items():
        (destination / name).write_text(content, encoding="utf-8")
    return {
        "generated": sorted(staged),
        "camera_fields": [
            "RT11", "RT12", "RT13", "RT21", "RT22", "RT23",
            "RT31", "RT32", "RT33", "TRX", "TRY", "TRZ",
            "OFX", "OFY", "H", "ZSF4",
        ],
        "target_faces": [[8,19,0], [11,11,0]],
        "event_stage": "camera_projection",
        "event_limit": "first normal-terrain processing of each target face",
        "gameplay_camera_captured": False,
        "original_assets_copied": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-modified-source", action="store_true")
    args = parser.parse_args()
    try:
        report = prepare(args.upstream, args.output_dir,
                         allow_modified=args.allow_modified_source)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    import json
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
