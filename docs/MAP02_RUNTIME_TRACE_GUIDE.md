# M_MAP02 runtime trace — instrumentation guide

Upstream baseline: `HalmyLyseas/VandalHearts-PcPort` at commit `14552fffa0e0b47e02b57592e274fc6e7a649923`. This is an **optional local diagnostic**, not a claim that the game has been traced. Do not commit original BIN, decompressed maps, or screenshots without checking distribution rights.

## Loader-side hook (confirmed source location)

In `src/states/game_setup.c`, `LoadMap()` calls `ProcessMapFileData()` at approximately line 2592 and converts local map GFX to global GFX inside the `iz`/`ix`/`iFace` loop at approximately lines 2600–2612. Insert an opt-in log **after the GFX conversion loops, before `SetupField()`** (roughly line 2614). The `pTiles` pointer used in the loop is `(MapTileModel(*)[28])gMapDataPtr`.

Suggested code fragment, assuming the host build supplies a suitable `printf` backend and includes `<stdio.h>`:

```c
#ifdef VH_TRACE_MAP02
if (gState.mapNum == 11) {
    MapTileModel (*tiles)[28] = (MapTileModel (*)[28])gMapDataPtr;
    printf("{\"z\":8,\"x\":19,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
           (int)tiles[8][19].gfx[0]);
    printf("{\"z\":11,\"x\":11,\"face\":0,\"stage\":\"post_load\",\"gfx\":%d}\n",
           (int)tiles[11][11].gfx[0]);
}
#endif
```

Do **not** execute this in a production build without verifying the logging backend. The snippet uses JSON Lines (one object per line). Convert those two lines into a JSON array for `tools/verify_map02_trace.py`, or adapt the logger to append to an array. Ensure the map number is 11 (the game's map identifier), even though the resource basename is `M_MAP02`.

## Draw-side observations

At the actual face-rendering callsite, capture matching objects using `stage: "draw"` and the *actual* global GFX just before primitive submission. Verify where face index and `z,x` are available rather than inferring them from framebuffer pixels. Also log primitive UV, CLUT, tpage, transparency flags, and frame number separately; the current validator consumes only GFX identity and does not prove visible rendering or palette correctness. A draw entry means the draw path was reached, **not** that a textured pixel was ultimately displayed.

After recording both stages for both faces, convert into a JSON array and invoke:

```sh
python3 -m tools.verify_map02_trace /local/path/map02_trace.json
```

Expected PRS post-load GFX: (8,19,0) → 641, (11,11,0) → 643. The DAT alternative is 498 and 550. Any mismatch or mutation warrants source-level investigation. Keep an original-game screenshot for later visual comparison. **No automatic texture rewrite** is authorized by this trace.
