#!/usr/bin/env python3
"""Produce a read-only, opt-in runtime trace patch for the pinned PC port.

The tool never modifies the upstream checkout. It emits a unified patch for
LoadMap and the three normal/edge/overhead terrain render paths. The patch
contains source code only, not original game resources.
"""
import argparse
import difflib
from pathlib import Path
import re
import subprocess

UPSTREAM_COMMIT = "14552fffa0e0b47e02b57592e274fc6e7a649923"
LOADER_PATH = "src/states/game_setup.c"
GRAPHICS_PATH = "src/core/graphics.c"
FLAG = "VH_TRACE_MAP02"
INCLUDE = '#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)\n#include <stdio.h>\n#endif\n'


def replace_once(source: str, anchor: str, replacement: str, label: str) -> str:
    count = source.count(anchor)
    if count != 1:
        raise ValueError(f"{label}: expected exactly one insertion anchor, found {count}")
    return source.replace(anchor, replacement, 1)


def instrument_loader(source: str) -> str:
    if FLAG in source:
        raise ValueError("loader already has VH_TRACE_MAP02 instrumentation")
    source = replace_once(source, '#include "field.h"\n',
                          '#include "field.h"\n' + INCLUDE, "loader include")
    anchor = '   SetupField();\n}\n\nvoid SetupField(void) {'
    hook = r'''
#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)
   /* The resource is named M_MAP02, but the runtime map number is 11. */
   if (gState.mapNum == 11) {
      MapTileModel (*traceTiles)[28] = (MapTileModel (*)[28])gMapDataPtr;
      if (traceTiles[8][19].faceCt > 0) {
         printf("{\"z\":8,\"x\":19,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
                (int)traceTiles[8][19].gfx[0]);
      }
      if (traceTiles[11][11].faceCt > 0) {
         printf("{\"z\":11,\"x\":11,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
                (int)traceTiles[11][11].gfx[0]);
      }
   }
#endif

'''
    return replace_once(source, anchor, hook + anchor, "post-LoadMap hook")


def instrument_graphics(source: str) -> str:
    if FLAG in source:
        raise ValueError("graphics already has VH_TRACE_MAP02 instrumentation")
    helper = r'''
#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)
/* Called only for a face that reached AddPrim; this does not prove visibility. */
static void VH_Map02TraceDraw(const MapTileModel *tile, int face, int gfx,
                              const POLY_FT4 *poly, const char *path) {
   int z, x;
   if (gState.mapNum != 11 || face != 0) return;
   if (tile == &gMapRowPointers[8][19]) {
      z = 8;
      x = 19;
   } else if (tile == &gMapRowPointers[11][11]) {
      z = 11;
      x = 11;
   } else {
      return;
   }
   printf("{\"z\":%d,\"x\":%d,\"face\":0,\"stage\":\"draw\","
          "\"gfx\":%d,\"frame\":%u,\"u\":%u,\"v\":%u,"
          "\"clut\":%u,\"tpage\":%u,\"path\":\"%s\"}\n",
          z, x, gfx, (unsigned)gState.frameCounter,
          (unsigned)poly->u0, (unsigned)poly->v0,
          (unsigned)poly->clut, (unsigned)poly->tpage, path);
}

/* Explain why a target face was considered but not submitted to AddPrim. */
static void VH_Map02TraceSkip(const MapTileModel *tile, int face, int gfx,
                              const char *path, const char *reason) {
   int z, x;
   if (gState.mapNum != 11 || face != 0) return;
   if (tile == &gMapRowPointers[8][19]) {
      z = 8;
      x = 19;
   } else if (tile == &gMapRowPointers[11][11]) {
      z = 11;
      x = 11;
   } else {
      return;
   }
   printf("{\\"z\\":%d,\\"x\\":%d,\\"face\\":0,\\"stage\\":\\"skip\\","
          "\\"gfx\\":%d,\\"frame\\":%u,\\"path\\":\\"%s\\","
          "\\"reason\\":\\"%s\\"}\\n",
          z, x, gfx, (unsigned)gState.frameCounter, path, reason);
}
#endif

'''
    source = replace_once(source, '#include "PsyQ/gtemac.h"\n',
                          '#include "PsyQ/gtemac.h"\n' + INCLUDE + helper,
                          "graphics trace helper")
    names = (
        ("RenderMapTile", "RenderEdgeMapTile", "normal"),
        ("RenderEdgeMapTile", "RenderOverheadMapTile", "edge"),
        ("RenderOverheadMapTile", "GetBestViewOfTarget", "overhead"),
    )
    for name, next_name, path in names:
        begin_marker = f"void {name}("
        next_marker = ("\ns32 " if next_name == "GetBestViewOfTarget" else "\nvoid ") + f"{next_name}("
        start = source.find(begin_marker)
        end = source.find(next_marker, start)
        if start < 0 or end < 0:
            raise ValueError(f"cannot locate {name} function bounds")
        body = source[start:end]
        expr = re.compile(r'(?m)^([ \t]*)AddPrim\(ot \+ OT_SIZE - otz, poly\);$')
        matches = list(expr.finditer(body))
        if len(matches) != 1:
            raise ValueError(f"{name}: expected one AddPrim, found {len(matches)}")
        match = matches[0]
        indent = match.group(1)
        call = (
            f"{indent}#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)\n"
            f'{indent}VH_Map02TraceDraw(tileModel, faceIdx, gfx, poly, "{path}");\n'
            f"{indent}#endif\n"
        )
        body = body[:match.start()] + call + body[match.start():]

        # Normal/overhead paths reject zero-texture faces before projection.
        if name != "RenderEdgeMapTile":
            null_anchor = "      if (gfx != GFX_NULL) {"
            if body.count(null_anchor) != 1:
                raise ValueError(f"{name}: expected exactly one GFX_NULL guard")
            null_hook = (
                "      #if defined(PC_FEAT) && defined(VH_TRACE_MAP02)\\n"
                f'      if (gfx == GFX_NULL) VH_Map02TraceSkip(tileModel, faceIdx, gfx, "{path}", "null_gfx");\\n'
                "      #endif\\n"
            )
            body = body.replace(null_anchor, null_hook + null_anchor, 1)

        # Each path computes opz before the front-face test; distinguish culling.
        stop_anchor = "         gte_stopz(&opz);" if name != "RenderEdgeMapTile" else "      gte_stopz(&opz);"
        if body.count(stop_anchor) != 1:
            raise ValueError(f"{name}: expected exactly one GTE depth test")
        edge_gfx = "tileModel->gfx[faceIdx]" if name == "RenderEdgeMapTile" else "gfx"
        stop_hook = (
            "\\n#if defined(PC_FEAT) && defined(VH_TRACE_MAP02)\\n"
            f'      if (opz <= 0) VH_Map02TraceSkip(tileModel, faceIdx, {edge_gfx}, "{path}", "backface");\\n'
            "#endif"
        )
        body = body.replace(stop_anchor, stop_anchor + stop_hook, 1)
        source = source[:start] + body + source[end:]
    return source


def create_patch(loader: str, graphics: str) -> str:
    updates = (
        (LOADER_PATH, loader, instrument_loader(loader)),
        (GRAPHICS_PATH, graphics, instrument_graphics(graphics)),
    )
    chunks = []
    for path, old, new in updates:
        chunks.extend(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{path}", tofile=f"b/{path}",
        ))
    return "".join(chunks)


def git_text(upstream: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(upstream), *args], capture_output=True,
        text=True, check=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, help="local PC-port checkout at pinned revision")
    parser.add_argument("--output", type=Path, required=True, help="output .patch file")
    args = parser.parse_args()
    root = args.upstream.resolve()
    try:
        sha = git_text(root, "rev-parse", "HEAD")
        if sha != UPSTREAM_COMMIT:
            raise ValueError(f"expected upstream commit {UPSTREAM_COMMIT}; got {sha}")
        if git_text(root, "status", "--porcelain", "--", LOADER_PATH, GRAPHICS_PATH):
            raise ValueError("upstream target files have uncommitted edits")
        patch = create_patch(
            (root / LOADER_PATH).read_text(encoding="utf-8"),
            (root / GRAPHICS_PATH).read_text(encoding="utf-8"),
        )
        if not patch:
            raise ValueError("empty patch")
        with args.output.open("x", encoding="utf-8") as output:
            output.write(patch)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))
    print(f"Wrote optional instrumentation patch to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
