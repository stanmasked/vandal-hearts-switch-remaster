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
GFX or recorded UV/CLUT/tpage across frames. In the default/legacy
validator, two draws of the same face within one frame and path remain a
duplicate error. Full-trace validation (`--require-full-trace`) allows two
such draws **only if a fresh nonempty `visit` precedes each separate render
call**. Without `frame`, older single-observation behavior is preserved.

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

The combined diagnostic patch now emits a `visit` event at entry to each
terrain renderer for each target tile, **before** iterating over its faces.
Each event records `frame`, `path`, `face_count` and the first face's
global `gfx`, or `gfx: 0` if `face_count: 0`. This captures the case where
the renderer reaches a tile with no faces: formerly neither `draw` nor
`skip` could describe it. The checker validates `face_count` (0–18)
and reports `visit_observation_count`, `visit_paths`,
`observed_face_counts` and a more specific `draw_status`:

- `submitted`: at least one `draw` event
- `skipped_in_observed_passes`: no draw, at least one `skip`
- `no_faces_in_observed_passes`: no draw/skip and all visits have zero faces
- `visited_without_submission`: at least one visit with a nonzero face count, but no recorded draw/skip
- `no_renderer_observation`: no draw, skip, or visit

A tile outside the current render window produces **no visit event**;
`no_renderer_observation` must not be interpreted as a missing texture.
Calls to a renderer may occur more than once with the same game frame counter;
`visit` counts all such calls and does not treat repetitions as duplicate errors.
A zero-face visit is not evidence of the original map bytes without a matching
`post_load` observation and provenance audit.

The new patch also records `skip` observations when a target face reaches
a terrain rendering function but is rejected before primitive submission:
`reason: "null_gfx"` when normal/overhead rendering encounters `GFX_NULL`,
or `reason: "backface"` when the GTE `opz <= 0` visibility check rejects
the face. Each event includes `frame`, `path`, and the observed GFX index.
The edge-render path has no `GFX_NULL` skip guard in the pinned source.
The trace checker reports a `draw_status` of `submitted`,
`skipped_in_observed_passes`, or `no_renderer_observation`, along with
`skip_reasons` and `skip_observation_count`.

A `skip` proves only that a particular rendering pass encountered and
rejected that face. It does not rule out submission via another path.
`no_renderer_observation` can mean the tile was outside the camera's
render window; it is **not proof of missing geometry**. The checker still
reports a missing `draw` event as an error in strict trace verification,
even when one or more skips explain why it might be absent. The `frame`
field is the game's observed `gState.frameCounter`, not a guaranteed count
of unique hardware refreshes.

All combined-patch `post_load`, `visit`, `skip` and `draw` events
now call `fflush(stdout)` immediately after each JSON line. PC-port
stdout is commonly redirected into a pipe or log file and may otherwise be
block buffered, losing the last observations if the process exits without
normal stdio cleanup. A host regression compiles the actual generated C
emitters and ends the process with `_Exit(0)` (which skips stdio cleanup);
it verifies that every emitted JSON event survives and still passes the
trace validator. Flushing is not a guarantee against an interrupted write,
an operating-system failure or missing observations when code is never
executed. Full tracing may generate significant output; keep raw logs for
diagnosis and avoid shipping it in production builds.

The log records `post_load` for each target face when map 11 loads and
`draw` immediately before `AddPrim` when a target face survives the
renderer visibility check. Draw samples have a `frame` number,
`path` (normal, edge, overhead), GFX, UV, packed GPU CLUT ID and tpage ID.
The validator recognizes `path` values `normal`, `edge`, and `overhead`, and preserves distinct render-path observations for the same face and frame. In legacy mode it rejects duplicates within the same face/frame/path; a trace may omit `path` for legacy single-path captures, but cannot mix annotated and unannotated observations for the same face.
For logs containing only JSON observation lines:

```sh
python3 -m tools.verify_map02_trace /local/map02-trace.jsonl
```

If stdout contains other diagnostics, separate the JSON observation lines
before validation; do not assume the entire process log is JSONL. Camera
culling, overhead view, other changing state and repeated draws can affect
whether events are emitted. Repeated observations in one frame on the
same renderer path require a new preceding nonempty `visit` in strict
full-trace mode; absent that visit, repeated `draw` or `skip` events are
reported as duplicates. Distinct annotated render paths remain independent. GitHub Actions now checks that the patch applies
cleanly to the pinned upstream revision, then **syntax-compiles both instrumented
C translation units** with the upstream PC game compiler flags and
`-DVH_TRACE_MAP02`. This is not a full linked PC executable or gameplay run;
there is still no runtime capture from original game data. It does **not** prove
that the submitted primitive contributed visible pixels or that the source
artwork is correct.


CI source-compilation verification: [Map02 upstream trace patch verification](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/map02-upstream-trace.yml).

## Noninvasive PC-port diagnostic build (prepared overlay)

The repository now provides a one-command **build preparation** that composes
both instrumentation generators, producing two diagnostic C translation units
and a makefile overlay **outside the upstream checkout**. It does not modify the
PC-port checkout or distribute disc data. Use the pinned upstream revision
`14552fffa0e0b47e02b57592e274fc6e7a649923` (US source tree).

From the remaster repository root:

```sh
python3 -m tools.prepare_map02_pcport   /absolute/path/to/VandalHearts-PcPort   /tmp/vh-map02-trace-01
```

For the **full diagnostic trace**, use `--full-trace` and a new output
directory. Unlike the default legacy mode, this connects the combined
instrumentation to the noninvasive build overlay without applying a patch
to the upstream checkout:

```sh
python3 -m tools.prepare_map02_pcport \
  /absolute/path/to/VandalHearts-PcPort \
  /tmp/vh-map02-full-trace --full-trace
cd /absolute/path/to/VandalHearts-PcPort/platform/pc
make -f Makefile -f /tmp/vh-map02-full-trace/map02_trace.mk \
  link BUILD_DIR=build-map02-full-trace
```

The full mode compiles both generated translation units with
`-DVH_TRACE_MAP02`. It records `post_load` plus every observed
`visit`, `skip` and `draw` event, including frame, path and packed GPU
metadata. The original default mode remains available for backwards
compatibility, uses `VH_TRACE_MAP02_POST_LOAD` and
`VH_TRACE_MAP02_DRAW`, and emits at most one draw per face per process.
`source_provenance.json` includes `trace_mode` (`full` or `legacy`).

GitHub Actions verifies that the full mode's generated make commands select
the trace sources, and compiles both full-mode object files against the
pinned upstream PC-port headers. This does **not** mean that the complete
game executable or original-resource runtime trace has been produced.

The destination directory must **not already exist** and must be outside the
PC-port tree. Paths with spaces or make-special characters are rejected. The
tool refuses incompatible upstream Makefile/source structure and verifies the
exact Git blob SHA-1 identities of `graphics.c`, `game_setup.c` and
`platform/pc/Makefile` against the pinned upstream revision. Every generated
directory contains `source_provenance.json` with independent SHA-256
fingerprints and a `matches_pinned` indicator for each source file.
Keep that file alongside captured runtime traces. The manifest also
contains SHA-256 digests for all three generated diagnostic build inputs:
`game_setup.trace.c`, `graphics.trace.c`, and `map02_trace.mk`.
The local capture tool verifies these fingerprints **before launching** the
supplied game executable, preventing an edited or missing generated
instrumentation source from silently retaining the original provenance.
Full-trace captures require these fingerprints; legacy manifests created
before this enhancement remain readable for compatibility.

In full-trace mode the generator additionally embeds two deterministic
identifiers: `VH_MAP02_TRACE_BUILD_ID:<sha256>` in the renderer and
`VH_MAP02_TRACE_LOADER_ID:<sha256>` in the loader. Both share the same
digest, calculated from the generated loader, renderer and Makefile-overlay
contents **before** either marker is inserted. They are recorded in
`source_provenance.json` as `binary_marker` and `binary_loader_marker`
and embedded as null-terminated C strings. The capture tool checks that
both exact identifiers occur in the selected executable **before launch**.
A regular PC-port binary, a build with only one instrumented module, or an
older/different full-trace build is rejected. CI verifies the two markers
in separate real Make-built object files and after partial linking.

This checks the presence of two build markers rather than cryptographically
attesting the entire executable or its runtime behavior. They can be copied,
removed by an incompatible stripping/linking configuration, or forged; matching
markers do not establish that all game objects came from the pinned
sources. Keep the instrumented object files, compiler
settings and binary SHA-256 with any decisive visual-reference comparison.

For a deliberately modified PC-port checkout, append
`--allow-modified-source` when preparing the diagnostic build and inspect
the provenance flags; such a build must not be described as the pinned
baseline. Only ASCII letters, digits, slashes, underscores, hyphens and
periods are supported in output directory paths, since Make shell commands
use those paths without quoting.

Then from the **upstream** `platform/pc` directory:

```sh
make -f Makefile -f /tmp/vh-map02-trace-01/map02_trace.mk   link BUILD_DIR=build-map02-trace
```

This uses upstream's original full build dependencies (SDL2, OpenAL,
OpenGL, game-derived build assets supplied locally) while replacing only the
two build inputs via explicit object recipes:

- `build-map02-trace/src/states/game_setup.o` compiles the generated
  `game_setup.trace.c` with `-DVH_TRACE_MAP02_POST_LOAD`.
- `build-map02-trace/src/core/graphics.o` compiles the generated
  `graphics.trace.c` with `-DVH_TRACE_MAP02_DRAW`.

The normal build folder and upstream sources remain untouched. The output
binary, if the build succeeds, is at
`platform/pc/build-map02-trace/vandalhearts_pc`.

Navigate to game map 11 using your own US disc data, arrange for both target
faces to be rendered, and capture stdout. Filter diagnostic JSON lines from
ordinary game logging before passing them to
`python3 -m tools.verify_map02_trace /local/path/map02_trace.jsonl`.
In default legacy mode, draw instrumentation emits at most one observation
per face per process. With `--full-trace`, events repeat across rendering
passes/frames, and all observations must be retained.
**A successful dry-run of make and a synthetic C smoke test do not prove that
the full game has compiled or that a real draw event was captured.**

The override and generator behavior are covered by host tests, including
`make -n` checks that each object uses the generated source and feature
flag. Run `make test` from the remaster repo for those tests. No proprietary
data should be committed to GitHub.

## Extracting trace events from mixed game logs

The PC port also prints ordinary SDL/renderer diagnostic messages, so capture
the unmodified combined stdout/stderr first. On a local PC-port diagnostic
build, for example:

```sh
./build-map02-trace/vandalhearts_pc 2>&1 | tee /tmp/vh-map02-game.log
```

From the **remaster** repository root, extract the tagged JSON objects
without changing the original log:

```sh
python3 -m tools.extract_map02_trace /tmp/vh-map02-game.log \
  -o /tmp/vh-map02-trace.jsonl
python3 -m tools.verify_map02_trace /tmp/vh-map02-trace.jsonl \
  --require-uniform-variant
```

Pass `--require-complete` to the extractor to demand a complete and
internally consistent two-face post-load/draw trace **before creating its
output**. An incomplete capture can still be extracted without that option
for investigation of `visit`/`skip` events. The extractor preserves all
observation events in order, including repeated entries, and rejects
malformed trace-looking JSON rather than silently deleting evidence. Other
console log lines are ignored. It never overwrites an existing output file.

Logs made by the alternative combined patch can include `visit` and
`skip` stages to explain missing submissions. Their presence is useful
evidence but **does not substitute for successful `draw` events** when
requiring complete rendering evidence. Do not commit raw game logs without
checking them for personal paths or copyrighted contents.

## Generated C-to-JSONL integration check (synthetic)

The host-only `tests/test_map02_trace_c_emitter.py` checks the whole logging
contract without loading proprietary game data. It takes the diagnostic
`printf` implementations generated for `LoadMap` and the renderer,
compiles them with GCC in an isolated **synthetic tile-model harness**, and
checks the resulting stdout with `tools.extract_map02_trace` and
`tools.verify_map02_trace`. The test covers consistent PRS and DAT
identifiers, `visit`/`skip`/`draw` ordering, packed CLUT/tpage fields,
and a zero-face tile that is visited but cannot emit a draw.

Run locally:

```sh
python3 -m unittest discover -s tests -p 'test_map02_trace_c_emitter.py' -v
```

The pinned-upstream patch CI also runs this test. Its success confirms that
the C trace format is compatible with both Python tools. **It does not
prove that the full PC port boots with the patch, that a real map uses either
variant, or that submitted polygons are visible in a framebuffer.**


## End-to-end host regression (synthetic map)

`tests/test_map02_renderer_smoke.py` now exercises the **whole diagnostic
data path** in one test suite: generate and compile a synthetic C renderer
with GCC/Clang, capture the emitted draw JSONL, mix it with ordinary
console messages and synthetic `post_load` observations, extract with
`tools.extract_map02_trace`, and validate with `tools.verify_map02_trace`.
It covers a stable PRS pair (641, 643), stable DAT pair (498, 550), and a
deliberate PRS-vs-DAT load/draw mismatch. A consistent DAT observation is
not automatically an error: the original resource discrepancy is
unresolved until actual gameplay or a reference capture distinguishes it.

From the remaster root:

```sh
python3 -m unittest discover -s tests -p 'test_map02_renderer_smoke.py' -v
```

These tests compile only the **synthetic** renderer. They do not supply
copyrighted game resources, prove that the PC-port game boots, or prove
which map variant is displayed on original hardware.

## One-command local runtime capture

After successfully building **your own** instrumented PC-port executable and
placing legally owned game data beside the executable as required by upstream,
you can capture a real session and analyze both disputed faces using a single
command. From the remaster repository root:

```sh
python3 -m tools.capture_map02_runtime   /absolute/path/to/VandalHearts-PcPort/platform/pc/build-map02-trace/vandalhearts_pc   /tmp/vh-map02-trace-01   /tmp/vh-map02-run-01
```

The middle argument points to the folder created by
`tools.prepare_map02_pcport` (it contains `source_provenance.json`).
The final argument is a **new**, non-existing directory. The command runs
the supplied executable in its own directory, streams its output to your
terminal while keeping an unaltered `game_stdout.log`, and waits until
you close the game. Navigate to **game map number 11**, make both disputed
faces visible to the renderer, and exit normally.

The capture writes extracted observations to `map02_trace.jsonl`
**while the game is still running**, flushing each record as it arrives.
Raw stdout/stderr bytes are saved in parallel to `game_stdout.log`.
The streaming decoder preserves UTF-8 and JSON lines split across pipe
reads, and it accepts a valid final record without a trailing newline.
A malformed trace-looking line causes a reported extraction error while
retaining the raw log and all already captured valid JSONL records;
partial evidence is never reported as a complete trace. At session end,
analysis reads the JSONL file one record at a time rather than materializing
the entire raw game log in memory. If the process never starts, the empty
derived JSONL is omitted and a failure report is kept.

The capture directory contains:

- `game_stdout.log` — byte-for-byte combined stdout/stderr, including non-UTF-8 bytes
- `map02_trace.jsonl` — extracted events, when any exist
- `capture_report.json` — consistency analysis, binary SHA-256,
  source provenance, game exit code, and independent SHA-256 + byte counts
  for raw stdout and derived JSONL (missing files are represented by null)

Once the game capture has finished (including an interrupted or
failed capture), verify its evidence bundle offline without the game assets:

```sh
python3 -m tools.verify_map02_capture /path/to/capture-directory
python3 -m tools.verify_map02_capture /path/to/capture-directory --require-complete
```

The verifier checks saved byte lengths and SHA-256 values, independently
replays the original `game_stdout.log` into Map02 events, compares every
extracted observation with `map02_trace.jsonl`, and recalculates the analysis
recorded in `capture_report.json`. It detects accidental edits or mismatched
files and also validates intentionally incomplete captures without claiming
that missing observations were seen. The strict option returns a nonzero
status for incomplete sessions even when their saved evidence is consistent.
This is a **consistency check, not a signed provenance guarantee**: a
deliberate actor controlling the files and report could rewrite all of them.

The script returns exit status 0 only when the game process exits successfully
and the analyzer has **no trace errors**; 1 means the game failed, 2 indicates
missing/incomplete/inconsistent trace. Both failure cases retain the raw log
and report. It never silently treats no observed face as success and never
overwrites an existing capture folder. Modified-source runs require
`--allow-modified-source` **before** the positional arguments.

The full-trace capture refuses to start if the executable lacks the exact
build marker recorded in the prepared diagnostic manifest. Existing legacy
captures do not require this marker. The marker check identifies an expected
diagnostic build but is not a signed build attestation and cannot prove
that every object in the executable came from the manifest. The executable SHA-256 allows
later identification of the exact binary tested. The raw log is written as bytes without UTF-8 replacement; decoding with
replacement occurs **only** in the JSON event extractor. A synthetic host
test confirms that invalid UTF-8 bytes survive the capture unchanged.
The diagnostics do not
download, upload, or modify any game data and cannot claim pixel-perfect
correctness from texture indices alone.

Host-only tests can exercise this capture procedure with a **fake PC-port
process** (no game data):

```sh
python3 -m unittest discover -s tests -p 'test_capture_map02_runtime.py' -v
```

These tests are separate from an actual play session. The assistant's
environment does not contain the user's game disc or a full playable binary,
so actual map02 game observations remain pending.


## Capture evidence integrity and failure handling

Before starting the game, `tools.capture_map02_runtime` checks that the
`git_blob_sha1` in each source record agrees with the pinned upstream Git
blob and the accompanying `matches_pinned` flag. It rejects malformed
source SHA-256 or Git SHA-1 values, rather than trusting a success boolean.
The diagnostic Make overlay and two generated C files are SHA-256 checked
for **both** `legacy` and `full` modes; a modified input is rejected
before a game process is launched.

The executable's SHA-256 is measured **before launch**, so the report still
identifies the original binary if its on-disk contents change later. If the
process fails to start, the capture folder now retains an empty or partial
`game_stdout.log` and a `capture_report.json` with `launch_error` and
the executable checksum. A closed terminal output pipe likewise does not
cancel the underlying raw-byte capture. Host regression tests simulate
those failures without copyrighted game data.

These are consistency and provenance checks, not a cryptographic signed
attestation tying every object in a binary to a particular source commit.
Game-map pixels and choice of PRS or DAT still require a real runtime
capture and reference comparison.


## Long-session capture and interrupted games

The capture helper now preserves a **partial report** when interrupted by
Ctrl+C. It requests termination of the child PC-port process, waits briefly
for remaining console output, and kills an unresponsive child if needed.
The report records `"interrupted": true` and the process exit code. Its
exit status remains **nonzero** even if four matching trace events happened
to be present before interruption, because the gameplay session was not
completed normally.

A busy PC port may produce a very large combined `game_stdout.log` during
a long map-11 session. Both `tools.capture_map02_runtime` and
`tools.extract_map02_trace` now **parse that file line by line** instead of
materializing the entire console log in memory. The complete original
capture is still saved byte-for-byte; only diagnostic JSON objects are
retained for the trace analyzer. Long trace sessions with many valid JSON
events can still consume memory proportional to the number of events.

The host regression tests cover a simulated keyboard interruption,
20,000 ordinary non-trace messages ahead of real event-format records,
and console logs containing invalid UTF-8 bytes. These do not constitute
a game runtime capture or verify a completed GitHub Actions run.


## Trace schema robustness (malformed events)

The verifier handles malformed JSON observation shapes without aborting:
`stage` must be one of `post_load`, `visit`, `skip`, or `draw`, and
must be a **string**. Arrays, objects, numbers, and null values are
reported as `invalid stage`; they must never crash a game-log analysis.
Likewise, draw `frame` must be a nonnegative integer (boolean values
are not accepted). Invalid frame entries are rejected **before** they can
change whether a face's draw stream is treated as framed or unframed.

The `null_gfx` skip reason is emitted only for GFX index **0**:
the pinned PC-port `include/graphics.h` defines `GFX_NULL = 0`.
The verifier now rejects a `null_gfx` skip with any other texture index,
so a corrupt observation cannot explain away a missing primitive.

Regression tests cover invalid stages including unhashable JSON arrays
and objects, invalid frame recovery, and a malformed-stage event passing
through a simulated game process, raw-byte capture, event extraction and
the final JSON report. This strengthens the diagnostics, but does not
resolve the original PRS/DAT discrepancy without actual gameplay evidence.


## Frame/path GFX consistency checks

The full-trace renderer records a `visit` when it enters a tile renderer,
then either a `draw` immediately before `AddPrim()` or a `skip`
describing a back-facing/empty-texture rejection. The validator now
correlates these events using **tile coordinates, face, frame and render
path** (`normal`, `edge`, or `overhead`).

For each context with a nonempty tile and a matching event, the face-0
GFX index at `visit` must agree with the later `draw` or `backface`
observation. A conflict is an error **even if `post_load` and `draw`
alone agree**. The report records the number of such checks per face
in `visit_draw_contexts_checked` and
`visit_backface_contexts_checked`. Multiple different visit GFX values
for the same frame and path also produce an error.

There are important boundaries to this check. Draws without a `frame`
or `path` (legacy trace format), visits of a tile with `face_count=0`,
and visits from *different* renderer paths are not silently paired.
Absence of a corresponding visit currently leaves this particular
cross-stage check at zero; it is not interpreted as proof that the face
was never reached. These checks detect contradictory diagnostic samples,
not the final visible pixels or which original resource is canonical.

Regression coverage includes a synthetic game process whose post-load
and draw GFX both report PRS (641), while the same-frame/same-path visit
reports DAT (498). The capture is correctly marked inconsistent even
though the two original endpoints matched.


## Strict full-trace ordering

The full instrumentation created by `prepare_map02_pcport --full-trace`
records a `visit` **before** a corresponding `draw` or `skip`
during each pass. An exact (tile, face, frame, path) match is required:
a visit in another frame or render path cannot justify a submission.
The visit must also show `face_count > 0`; a zero-face tile cannot
justify a subsequent face-0 draw. If one tile is visited several times
under the same game frame counter and path, the validator numbers its
successive visits and attributes at most one face-0 `draw` or `skip`
of each type to each nonempty visit. A new zero-face visit invalidates
the preceding nonempty visit for that context, preventing stale evidence
from authorizing a later draw. This is now enforced automatically by
`tools.capture_map02_runtime` when its preparation manifest declares
`trace_mode: full`.

Manual validation of a full trace can enforce the same requirement:

```sh
python3 -m tools.verify_map02_trace /path/to/map02_trace.jsonl --require-full-trace
python3 -m tools.extract_map02_trace /path/to/game_stdout.log \
  -o /path/to/strict-map02.jsonl --require-full-trace
```

The flags reject missing/out-of-order context rather than silently
accepting an otherwise matching PRS/DAT pair. Legacy traces from the
older first-draw hooks have no frame/path/visit fields and remain
supported **without** the flag.

The pinned PC-port defines `GFX_NULL = 0`. A nonempty visit may
legitimately record GFX 0 before a `null_gfx` skip, and the edge renderer
can likewise reject a zero-indexed face as back-facing. The verifier
accepts those observations; they do not satisfy the requirement to
record a genuine `draw` for both disputed faces. These consistency
checks still cannot prove visible pixels.


## One-outcome-per-visit renderer auditing

The pinned US PC-port emits a renderer `visit` when it enters a tile
renderer. For **map 11, face 0**, every nonempty visit must then take exactly
one of the instrumented outcomes: a textured `draw` handed to
`AddPrim()`, or a `skip` for `null_gfx` or `backface`.

In `--require-full-trace` mode, the analyzer tracks **individual
invocations** using the tile position, game frame, renderer path, and
successive visit number. It detects two particularly misleading cases:

- One visit followed by both `draw` and `skip` (or two different
  `skip` reasons) — impossible for face 0 in the audited renderer.
- A nonempty visit with no subsequent `draw` or `skip`, even if a
  later visit in the same frame/path completes normally.

Strict mode also verifies that a `null_gfx` skip follows a visit
reporting GFX 0. A `null_gfx` skip in the **edge** renderer is invalid:
that path has no null-texture rejection branch in pinned
`src/core/graphics.c`. Zero-face visits are allowed to have no
outcome because there is no face 0 to process.

The original lightweight (legacy) trace cannot provide this evidence
because it does not record individual renderer entry events. These
new checks therefore apply **only** to full-trace sessions. Regression
tests cover both impossible outcomes and independently verified capture
reports, without requiring game assets.

A full-trace session with contradictory or unfinished renderer events is
incomplete even when the top-level GFX values look like consistent
PRS (641/643) or DAT (498/550). This protects the texture comparison from
falsely accepting truncated evidence; final pixel visibility remains
unverified until a genuine gameplay capture is available.
