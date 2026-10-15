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

Do **not** execute this in a production build without verifying the logging backend. The snippet uses JSON Lines (one object per line). The checker now accepts both **JSON Lines** (as emitted by this snippet) and a JSON array directly. Retain both post-load and draw events in the same log. Ensure the map number is 11 (the game's map identifier), even though the resource basename is `M_MAP02`.

## Draw-side observations

At the actual face-rendering callsite, capture matching objects using `stage: "draw"` and the *actual* global GFX just before primitive submission. Verify where face index and `z,x` are available rather than inferring them from framebuffer pixels. Also log primitive UV, CLUT, tpage, transparency flags, and frame number separately; the current validator consumes only GFX identity and does not prove visible rendering or palette correctness. A draw entry means the draw path was reached, **not** that a textured pixel was ultimately displayed.

After recording both stages for both faces, save the JSON Lines output (or a JSON array) and invoke:

```sh
python3 -m tools.verify_map02_trace /local/path/map02_trace.json
```

Expected PRS post-load GFX: (8,19,0) → 641, (11,11,0) → 643. The DAT alternative is 498 and 550. Any mismatch or mutation warrants source-level investigation. Keep an original-game screenshot for later visual comparison. **No automatic texture rewrite** is authorized by this trace.

## Optional draw metadata (implemented)

The trace checker accepts additional integer keys on `stage: "draw"` entries:
`u`, `v` (0–255) and `clut`, `tpage` (0–65535). It preserves them in
`draw_metadata` and reports invalid types or ranges. Omitting these keys
keeps existing minimal trace logs compatible. These values are **observed GPU
metadata**, not independently checked against the original resource's palette
table or texture page. Gather them at primitive submission rather than copying
the known atlas values into a synthetic log.

Example of the expected **data shape only**, not an actual runtime observation:

```json
{"z":8,"x":19,"face":0,"stage":"draw","gfx":641,"u":240,"v":192,"clut":35,"tpage":5}
```


## Multi-frame capture

When tracing actual render loops, append an integer `frame` (starting at 0) to
each draw event. Repeated draw events for the same face in **different frames**
are expected, not duplicate records. The checker retains the first draw
observation, counts all frame-tagged draw samples, and reports any changes in
GFX or recorded UV/CLUT/tpage across frames. Two draw entries for the same
face and same `frame` remain an error. Without `frame`, the older
single-observation behavior is preserved.

Example shape (illustrative, not captured from an actual game):

```jsonl
{"z":8,"x":19,"face":0,"stage":"draw","gfx":641,"frame":1,"u":240,"v":192,"clut":35,"tpage":5}
{"z":8,"x":19,"face":0,"stage":"draw","gfx":641,"frame":2,"u":240,"v":192,"clut":35,"tpage":5}
```

Metadata that is absent from a sample cannot be compared. A stable trace
does not establish whether the pixel colors or geometry are visually correct.

## Automated local loader instrumentation

The repository includes a **read-only-to-input** code generator. Obtain the
upstream PC-port checkout at the pinned version yourself, then run:

```sh
python3 -m tools.instrument_map02_loader   /local/pcport/src/states/game_setup.c   /local/pcport/src/states/game_setup.map02trace.c
```

The output is a *separate source file*, not an automatic working build. To
use it, replace the original translation unit in a **local diagnostic build**;
do not compile both files, because they define the same functions. Compile
with `-DVH_TRACE_MAP02_POST_LOAD` and a functioning stdout/stderr
collection channel. The injector refuses missing or ambiguous source anchors,
and never overwrites its output. Logs contain two post-load JSON Lines for
game map 11. **Draw-side primitive instrumentation is still required**, and
no original assets are altered. The generator has not been compiled against
the complete upstream PC port or executed on console hardware.
