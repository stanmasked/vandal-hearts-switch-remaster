#!/usr/bin/env python3
"""Generate opt-in map02 draw tracing from the pinned upstream graphics.c.

Produces a new C file; never modifies original sources or game assets.
The trace captures one submitted primitive per disputed face, not each frame.
"""
import argparse
import re
from pathlib import Path

GUARD = "VH_TRACE_MAP02_DRAW"
FUNCTIONS = ("RenderMapTile", "RenderEdgeMapTile", "RenderOverheadMapTile")
HELPER = r'''#ifdef VH_TRACE_MAP02_DRAW
/* Two disputed M_MAP02.PRS tile faces in game map 11. */
static unsigned char vh_map02_draw_seen[2] = {0, 0};
static void vh_trace_map02_draw(const MapTileModel *tile, int face,
                                int gfx, const POLY_FT4 *poly) {
   int index, z, x;
   if (gState.mapNum != 11 || face != 0) return;
   if (tile == &gMapRowPointers[8][19]) {
      index = 0; z = 8; x = 19;
   } else if (tile == &gMapRowPointers[11][11]) {
      index = 1; z = 11; x = 11;
   } else {
      return;
   }
   if (vh_map02_draw_seen[index]) return;
   vh_map02_draw_seen[index] = 1;
   printf("{\"z\":%d,\"x\":%d,\"face\":0,\"stage\":\"draw\",\"gfx\":%d,\"u\":%u,\"v\":%u,\"clut\":%u,\"tpage\":%u}\n",
          z, x, gfx, (unsigned)poly->u0, (unsigned)poly->v0,
          (unsigned)poly->clut, (unsigned)poly->tpage);
}
#endif
'''
DRAW_CALL = '''#ifdef VH_TRACE_MAP02_DRAW
{indent}vh_trace_map02_draw(tileModel, faceIdx, gfx, poly);
#endif
'''
ADD_PRIM = re.compile(r"(?m)^([ \t]*)AddPrim\(ot \+ OT_SIZE - otz, poly\);$")


def instrument(source: str) -> str:
    if GUARD in source:
        raise ValueError("source already instrumented")
    marker = "void RenderMapTile(u32 *ot, MapTileModel *tileModel, s32 gridColor) {"
    if source.count(marker) != 1:
        raise ValueError("RenderMapTile anchor must occur exactly once")
    for name in FUNCTIONS:
        if source.count(f"void {name}(") != 1:
            raise ValueError(f"{name} function must occur exactly once")
    # Only transform bodies of the three confirmed tile-rendering functions.
    indices = [source.index(f"void {name}(") for name in FUNCTIONS]
    if indices != sorted(indices):
        raise ValueError("unexpected tile rendering function order")
    tail_marker = "s32 GetBestViewOfTarget("
    if source.count(tail_marker) != 1 or source.index(tail_marker) <= indices[-1]:
        raise ValueError("end of RenderOverheadMapTile not found")
    ends = indices[1:] + [source.index(tail_marker)]
    modified = source
    for start, end, name in reversed(list(zip(indices, ends, FUNCTIONS))):
        body = modified[start:end]
        if len(ADD_PRIM.findall(body)) != 1:
            raise ValueError(f"{name}: expected exactly one primitive submission")
        if "gfx = tileModel->gfx[faceIdx];" not in body:
            raise ValueError(f"{name}: per-face GFX lookup not found")
        if "poly->clut = gGfxClutIds[gfx];" not in body or "poly->tpage = gGfxTPageIds[gfx];" not in body:
            raise ValueError(f"{name}: primitive texture metadata lookup not found")
        if "poly->code = GPU_CODE_POLY_FT4;" not in body:
            raise ValueError(f"{name}: textured quad submission not found")
        def replace(match):
            indent = match.group(1)
            return DRAW_CALL.format(indent=indent) + match.group(0)
        body = ADD_PRIM.sub(replace, body, count=1)
        modified = modified[:start] + body + modified[end:]
    return '#include <stdio.h>\n' + modified.replace(marker, HELPER + '\n' + marker, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="upstream src/core/graphics.c")
    parser.add_argument("output", type=Path, help="new instrumented graphics.c (must not exist)")
    args = parser.parse_args()
    try:
        source = args.input.read_text(encoding="utf-8")
        result = instrument(source)
        if args.input.resolve() == args.output.resolve():
            parser.error("input and output must differ")
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(result)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Created {args.output}; enable with -DVH_TRACE_MAP02_DRAW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
