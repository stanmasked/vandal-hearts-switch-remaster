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

## Automated draw-side instrumentation (three renderer paths)

The pinned upstream renderer `src/core/graphics.c` has **three distinct**
textured tile render functions:

- `RenderMapTile` (interior field tiles)
- `RenderEdgeMapTile` (edge tiles)
- `RenderOverheadMapTile` (overhead map view)

Each populates a `POLY_FT4` quad and submits it via `AddPrim`. To instrument all
three without changing upstream sources in place:

```sh
python3 -m tools.instrument_map02_renderer   /local/pcport/src/core/graphics.c   /local/pcport/src/core/graphics.map02trace.c
```

For a **local diagnostic build only**, compile the generated
`graphics.map02trace.c` *instead of* the original `graphics.c`, with
`-DVH_TRACE_MAP02_DRAW` and functioning stdout collection. Similarly compile
the previously generated `game_setup.map02trace.c` instead of the original
`game_setup.c`, with `-DVH_TRACE_MAP02_POST_LOAD`. Never compile both an
original and its generated replacement into the same executable.

The draw hook triggers immediately before a PS1-style textured primitive is
handed to `AddPrim`, for face 0 of the **actual** tile-model pointers at
(z=8,x=19) or (z=11,x=11), only when `gState.mapNum == 11`. It prints **at
most one draw event per target face per process**. This deliberately avoids
overwhelming stdout and is compatible with the validator's unframed JSONL
mode. For continuous per-frame capture, more invasive instrumentation and
frame synchronization would be required.

The values `u` and `v` are the primitive's UV fields, whereas `clut`
and `tpage` are packed **GPU primitive IDs**, **not** the raw LAND_DT
palette number (33 or 35) or atlas cell index (5). Do not compare those
numbers directly. Absence of a draw entry can indicate camera culling or an
unvisited rendering path, not necessarily missing geometry. A draw entry
indicates submission, not guaranteed final pixels.

The injector checks source anchors and refuses overwriting existing output
files; its regression tests run with `make test`. These are generator
tests: successful end-to-end compilation and runtime capture in the PC port
are **not yet confirmed**. No copyrighted game bytes are added to this repo.


## Alternative: one combined patch for multi-frame captures

The optional `tools/make_map02_trace_patch.py` generates a **single unified
patch** against upstream commit `14552fffa0e0b47e02b57592e274fc6e7a649923`.
Unlike the two separate source-file generators above, it adds post-LoadMap and
all three terrain submission hooks in one patch, with draw-frame numbers.
**Choose one approach; do not combine instrumentation generated by both.**

From the remaster repository, with a clean checkout of the pinned PC port:

```sh
python3 -m tools.make_map02_trace_patch /local/pcport --output /local/map02-trace.patch
cd /local/pcport
git apply --check /local/map02-trace.patch
git apply /local/map02-trace.patch
# Build an optional PC diagnostic executable with -DVH_TRACE_MAP02.
# Also ensure PC_FEAT is defined and stdout is available.
```

The generator checks the exact upstream HEAD, clean target files, unique
source anchors and refuses to overwrite an existing patch file. It **never
edits the checkout itself**; `git apply` is a separate, explicit local
operation. Do not push this instrumentation into a distribution build.
To revert this local experiment after the capture, use
`git apply -R /local/map02-trace.patch` (after checking for any other edits).

The log records `post_load` for each target face when map 11 loads and
`draw` immediately before `AddPrim` when a target face survives the
renderer visibility check. Draw samples have a `frame` number,
`path` (normal, edge, overhead), GFX, UV, packed GPU CLUT ID and tpage ID.
The `path` field is informational and ignored by the current validator.
For logs containing only JSON observation lines:

```sh
python3 -m tools.verify_map02_trace /local/map02-trace.jsonl
```

If stdout contains other diagnostics, separate the JSON observation lines
before validation; do not assume the entire process log is JSONL. Camera
culling, overhead view, other changing state and repeated draws can affect
whether events are emitted. A single face observed multiple times in one frame
may be rejected by the present validator and merits inspection instead of
silently dropping records. The patch has not yet been compiled against the
complete PC port or executed with original game data. It does **not** prove
that the submitted primitive contributed visible pixels or that the source
artwork is correct.
