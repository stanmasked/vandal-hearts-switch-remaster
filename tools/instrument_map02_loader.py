#!/usr/bin/env python3
"""Generate a local, opt-in map02 post-load trace build from upstream game_setup.c.

Never edits the user's input; emits a separately named C file. Uses exact
upstream structural anchors and refuses ambiguous or already-patched input.
The output still requires an upstream host build with working stdout.
"""
import argparse
from pathlib import Path

ANCHOR = "   SetupField();\n}\n\nvoid SetupField(void) {"
GUARD = "VH_TRACE_MAP02_POST_LOAD"
TRACE = r'''#ifdef VH_TRACE_MAP02_POST_LOAD
   if (gState.mapNum == 11) {
      MapTileModel (*traceTiles)[28] = (MapTileModel (*)[28])gMapDataPtr;
      printf("{\"z\":8,\"x\":19,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
             (int)traceTiles[8][19].gfx[0]);
      printf("{\"z\":11,\"x\":11,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
             (int)traceTiles[11][11].gfx[0]);
   }
#endif
'''


def instrument(source: str) -> str:
    if GUARD in source:
        raise ValueError("source is already instrumented")
    if source.count(ANCHOR) != 1:
        raise ValueError("expected exactly one LoadMap-to-SetupField anchor")
    if "ProcessMapFileData(&gScratch1_801317c0[0]);" not in source:
        raise ValueError("map decompression call not found")
    if "pTiles[iz][ix].gfx[iFace] += GFX_MAP_TEXTURES_OFS;" not in source:
        raise ValueError("global GFX conversion not found")
    return source.replace(ANCHOR, TRACE + "\n" + ANCHOR, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="upstream src/states/game_setup.c")
    parser.add_argument("output", type=Path, help="NEW instrumented C file (never overwrite)")
    args = parser.parse_args()
    try:
        src = args.input.read_text(encoding="utf-8")
        result = instrument(src)
        if args.input.resolve() == args.output.resolve():
            parser.error("input and output must differ")
        with args.output.open("x", encoding="utf-8") as handle:
            handle.write('#include <stdio.h>\n' + result)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Created {args.output}. Compile with -DVH_TRACE_MAP02_POST_LOAD to enable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
