# MAP02 unified native-scoped WritePixel + BlendG1 diagnostic patch

The old `instrument_map02_native_writepixel.py` and
`instrument_map02_blendg1_call.py` generators both insist on pristine
`pc_raster.c`, so they cannot be stacked. Use the new
`tools/instrument_map02_scoped_blend.py` for a **single** source copy
containing both observations.

```sh
python3 -m tools.instrument_map02_scoped_blend \
  /private/original/platform/pc/src/pc_raster.c \
  /private/build/pc_raster.map02-scoped.c
python3 -m unittest -v tests.test_instrument_map02_scoped_blend
```

The input must be pristine and the output must not exist. Anchors are checked
exactly once. The tool does not touch the input and refuses ambiguous or
previously modified sources. `VH_MAP02_SCOPED_BLEND_PROBE` controls all
instrumentation at compilation time; the generated source compiles with the
macro absent and retains the existing pixel arithmetic.

## Three callbacks (private harness required)

```c
void vh_map02_probe_begin(int x, int y, unsigned short before,
    unsigned short front, int abr, int semi, int textured, int accurate);
void vh_map02_probe_blendg1(int x, int y, unsigned short fg,
    unsigned short bg, unsigned short result, int abr, int textured);
void vh_map02_probe_end(int x, int y, unsigned short after);
```

For native VRAM, the C call sequence is `begin -> [optional BlendG1] ->
end`, where the middle call exists **only** for accurate semitransparent
rasterization. Legacy semitransparency has no BlendG1 callback and requires
separate analysis. Supersampled `s_hires` writes produce no callbacks.

The **actual** BlendG1 call supplies `fg` with forced bit 15 and the
original background `bg`, plus the actual returned BGR555 word. Begin/end
carry the original PutPixel front and its native VRAM before/after.
The callbacks must be nonrecursive, bounded, thread-scoped, and coordinate
filtered. They must never publish raw color words, coordinates, screenshots,
or original game content in CI artifacts.

This stage supplies **neither callback implementations nor the verified
DrawOTag frame, primitive ordinal, and step context**. The private harness
must obtain those markers directly from the GPU observer and connect them
to callbacks, without deriving them from after-the-fact PutPixel logs.
It must reject event overflow, missing callbacks, mode changes between
begin/end, cross-thread mixing, and context mismatches.

The standalone `verify_map02_blendg1_witness.py` still requires
SHA-bound independently observed witness events containing those markers.
A source patch alone cannot authenticate a real MAP02 capture or prove
PlayStation hardware blending.

## Regression scope

`tests/test_instrument_map02_scoped_blend.py` covers exact source anchors,
duplicate/drift rejection, macro-off compilation, macro-on compilation and
execution of a synthetic C rasterizer (where a native accurate write
produces one BlendG1 callback, HD produces none, and legacy semi is
begin/end only). GitHub Actions workflow:
`.github/workflows/map02-scoped-blend.yml`.

This synthetic test is not a genuine source-port build or game rendering.

## Upstream DrawOTag context confirmed

In original `platform/pc/src/libgpu.c`, `DrawOTag` increments
`s_drawFrame` at the start of each frame. Its OT walker resolves tokens
and skips bucket nodes before handling real primitives. A private shim
must therefore count **native raster draw entries (F4/FT4/SPRT/TILE)**,
not every non-bucket item or raw OT walk step, when supplying `primitive_ordinal`. It must explicitly bind
the active frame and ordinal to the native raster call before opening
the scoped PutPixel witness, and clear that context afterward.

No such context shim has been installed in this stage; neither the
generator nor its test fabricates `frame`, `primitive_ordinal`, or
`putpixel_step`. This prevents the synthetic C regression from being
mistaken for authenticated original gameplay capture.

## Bounded private in-memory sink (experimental)

`tools/map02_scoped_blend_sink.h` and
`tools/map02_scoped_blend_sink.c` now implement the three observer
callbacks and a strict one-frame, coordinate-scoped state machine.
The private test harness must call:

```c
vh_map02_scope_reset();
vh_map02_scope_begin_frame(frame, target_x, target_y);
/* once per native DRAW operation (F4/FT4/SPRT/TILE), starting at zero: */
vh_map02_scope_begin_primitive(ordinal, primitive_type);
/* native rasterization invokes begin / optional BlendG1 / end */
vh_map02_scope_end_primitive();
vh_map02_scope_end_frame();
```

All context setters return nonzero on success. The capture accepts
at most **63 completed pixel events**, tracks `step` from zero, and
rejects missing/repeated `BlendG1`, wrong bit 15, disagreement between
observed inputs/results, noncontiguous primitive ordinals, invalid ABR
or mode flags, unfinished pixel calls and capacity overflow. A failure
is sticky; `vh_map02_scope_copy` refuses to export any events until
the frame is successfully closed. No file or network I/O is performed.
Call `vh_map02_scope_reset` to erase the buffer before another capture.

**These context methods are NOT yet inserted into the upstream DrawOTag
walker.** The values provided by a private harness remain untrusted
until a separately instrumented original-PC path proves they came from
the active walker. The sink must run on the synchronous native-raster
thread; it is not designed for concurrent callbacks. An unobserved
HD worker cannot be used as a proxy for native writes.

Host tests `tests/test_map02_scoped_blend_sink.py` and
`tests/test_map02_scoped_blend_integration.py` exercise the synthetic
C state machine and generated code together. The CI workflow now also
checks source-anchor compatibility against a pinned public upstream
commit `14552fffa0e0b47e02b57592e274fc6e7a649923`, without
committing or publishing upstream game assets. This step only generates
the patched source; it does not build or run the actual PC game.

No captured frame has been authenticated. The standalone SHA-bound
BlendG1 JSONL verifier still requires a separate private harness
to serialize successfully closed observations, with independently
validated provenance.

## Direct DrawOTag frame/ordinal binding (opt-in)

`tools/instrument_map02_drawotag_scope.py` now creates a separate modified
copy of original `platform/pc/src/libgpu.c`. Use it **together** with
`tools/instrument_map02_scoped_blend.py` on copies from the same pinned
upstream revision. Both are disabled unless the
`VH_MAP02_SCOPED_BLEND_PROBE` C macro is explicitly enabled.

```sh
python3 -m tools.instrument_map02_drawotag_scope \
  /private/upstream/platform/pc/src/libgpu.c \
  /private/build/libgpu.map02-scoped.c
```

The diagnostic library must link
`tools/map02_scoped_blend_sink.c` with the generated rasterizer and GPU
walker. Select **one** target frame and private native-VRAM coordinate
using all three decimal environment variables:

```text
VH_MAP02_PROBE_FRAME=123
VH_MAP02_PROBE_X=100
VH_MAP02_PROBE_Y=100
```

Frame must be 1..4294967295, X 0..1023, Y 0..511. Missing all
variables disables capture. Partial, malformed, overflowing and
out-of-range configurations invalidate the sink and cannot publish
events. All decimal strings are parsed strictly, with no sign or suffix.

The patch reads actual `s_drawFrame` immediately after increment in
`DrawOTag`; a primitive ordinal starts at zero and increases for
**each native raster draw** (F4/FT4/SPRT/TILE) in the original OT walker.
Bucket nodes, DR_MODE commands and unsupported packets do not advance it;
this matches the native VRAM before/after draw-pair verifier. The observer opens the primitive before its switch
dispatch and closes it after. Invalid token resolution or OT cycle
limits abort the capture; a completed target frame is sealed **before**
deferred HD workers begin. No raw pixel data are emitted.

`tests/test_instrument_map02_drawotag_scope.py` uses a synthetic
bucket/primitive chain to check frame binding, raster-draw ordinal tracking, invalid-token failure, strict opt-in configuration and
macro-on/off C compilation. Pinned upstream source-anchor
compatibility is included in
`.github/workflows/map02-scoped-blend.yml`.

**Not yet done:** a build of the complete original PC port with both
instrumented translation units, private witness serialization into the
SHA-bound manifest/JSONL format, and authenticated MAP02 gameplay
capture. Synthetic tests do not establish genuine frame provenance
beyond their test input, and no claim of physical PS1 accuracy follows.

## Private in-memory JSONL bridge

The bounded sink now retains the **native primitive type** decoded by the
original `DrawOTag` walker, in addition to the frame, draw-only ordinal,
and local PutPixel step. Primitive types outside 0..255 cause a sticky
capture failure; type and ordinal are independently checked again by the
Python witness comparator.

Two formatter functions are available **only after a complete, successful
frame capture**:

```c
int vh_map02_scope_format_putpixel(unsigned index, char *dst,
                                   unsigned capacity);
int vh_map02_scope_format_blendg1(unsigned index, char *dst,
                                  unsigned capacity);
```

Both return the number of bytes written, excluding the terminating NUL,
or zero if capture is incomplete/invalid, the index is out of range, a
buffer is too small, or a requested BlendG1 event does not exist.
The result is a newline-delimited JSON record in caller-owned memory.
No file is created, no private colors or coordinates are uploaded, and
the serializer does not construct BlendG1 observations from PutPixel:
the three BlendG1 words are populated exclusively by the actual-call
callback. A private harness must handle file permissions, durable
storage, input hashes, and comparison against verified VRAM snapshots.

The new `tests/test_map02_scoped_blend_jsonl_bridge.py` compiles a
synthetic C producer, decodes its JSONL with Python, and passes the
records into `compare_blendg1_witnesses`. It checks an accurate
BlendG1 event, legacy semi-transparent path without BlendG1, and
opaque copy, including rejection of forged primitive type and missing
BlendG1 fields.

The state machine also now ignores callbacks outside the selected
frame, including before opt-in and after a sealed frame; an explicitly
aborted selected capture remains permanently invalid until reset.
This prevents incidental writes at coordinate (0,0) from corrupting
a capture when no frame was selected.

**Remaining:** explicitly scoped, private persistence and SHA-256
binding to independently captured native DrawOTag/VRAM evidence; complete
instrumented PC-port build; genuine MAP02 frame comparison; PS1 hardware
verification. None is claimed by synthetic host tests.

## Private, SHA-bound witness publication (experimental)

A separate opt-in publisher now exists:
`tools/publish_map02_blendg1_witness.py`. It does **not** collect
BlendG1 calls; the private original-PC harness must first write the
bounded, directly observed `blendg1-native-events.pending.jsonl` into
the native capture directory. The pre-existing
`putpixel-native-events.jsonl` and `gpu-putpixel-ot.json` must already
be present and bound to verified native DrawOTag/VRAM evidence.

```sh
python3 -m tools.publish_map02_blendg1_witness \
  /private/map02/source-bundle \
  /private/map02/native-capture
python3 -m tools.verify_map02_blendg1_witness \
  /private/map02/source-bundle \
  /private/map02/native-capture
```

Both directories must already exist with private permissions (0700)
and must not be symlinks. Source files must be regular, non-symlinked,
bounded in size, valid JSONL with final newlines, and
`putpixel_events_sha256` must match the upstream manifest. Publication
calls the **full** upstream `verify_pixel_ot` (including source-keyed
DrawOTag/VRAM checks) and the strict
`compare_blendg1_witnesses` comparator; there is no option to skip
this verification in the CLI. Input files are read again after the
upstream verifier to reject changes during verification.

After validation, both finished files are written to private 0600
temporary files, synced, read back byte-for-byte and installed using
exclusive hard links. The completed `blendg1-native-events.jsonl`
is published in the native capture directory first; the
`gpu-blendg1-witness.json` completion manifest is published **last**
in the source bundle. Both must be absent before publication; there
is no overwrite operation. A failed publication attempts to remove
newly created outputs and temporary files, leaving no trusted
completion marker. A process crash may leave an orphaned log without a
manifest; it is **not** validated evidence and must be investigated
privately before a new attempt. The publisher never prints raw pixel
words, event coordinates, screenshots, game assets, or log contents.

The manifest uses schema `vh.map02.native-blendg1-witness.v1`,
containing SHA-256 for the original PutPixel manifest, the original
PutPixel log and the independently staged BlendG1 log. The standalone
`verify_map02_blendg1_witness.py` must subsequently verify the
published witness again. A valid synthetic fixture or SHA-bound
original-PC observation still does **not** establish that MAP02
gameplay actually occurred or that the result matches PS1 hardware.

Synthetic no-clobber, missing-witness, tampering, rollback and private
directory tests:
`tests/test_publish_map02_blendg1_witness.py` (CI workflow
`.github/workflows/map02-scoped-blend.yml`).

Both the publisher and the final witness verifier use the **same**
strict framing rules: UTF-8 JSON objects, exactly one final LF per
nonempty JSONL row, no CRLF or blank rows, and fewer than 64 events per
stream. The staged log is checked before any final file is created.
A completed marker does not exempt a log from independent revalidation.

## POSIX private staged export from the original DrawOTag walker

A separate POSIX-only stage writer is now available:
`tools/map02_scoped_blend_stage.c/.h`. Link it together with the scoped
sink and the two patched PC-port translation units, and define both
`VH_MAP02_SCOPED_BLEND_PROBE` and `VH_MAP02_POSIX_STAGE` in this
**private diagnostic build**. The second macro is deliberately separate
so Windows builds and the ordinary render path do not depend on POSIX
file functions.

With all existing frame/X/Y variables configured, explicitly opt in to
disk staging through:

```sh
# This directory must already exist, be owned by the current user,
# and have exactly 0700 permissions.
export VH_MAP02_PROBE_OUTPUT_DIR=/private/map02/native-capture
```

At the end of the selected `DrawOTag` frame, **before deferred HD
workers run**, the instrumented walker first seals the bounded native
VRAM event buffer. Only if the seal succeeds does it call
`vh_map02_stage_private_blendg1`. If no output directory is
specified, all records remain in memory. An explicitly set empty or
invalid output path causes the capture to fail closed. No files are
written from ordinary gameplay builds without both macros.

The staging writer:

- collects **only observed accurate-mode BlendG1** records from the
  sealed native VRAM buffer, never reconstructing them from PutPixel;
- limits the pending log to 16 KiB and requires a final LF;
- checks that the destination is a non-symlinked, owned POSIX directory
  with mode 0700;
- creates a private 0600 temporary file without following symlinks,
  checks write/fsync, rereads and compares every byte;
- publishes `blendg1-native-events.pending.jsonl` with an **exclusive
  hard link**, preventing overwrite and refusing an existing file;
- syncs the directory and removes the temporary name; on failure,
  attempts to roll back any file created by the current call.

There is no printed game data, no automatic GitHub upload, no overwrite
or synthetic witness generation. Crash recovery is intentionally manual:
an orphaned pending file or stale temporary file must never be treated
as verified evidence. It is only input to the independent
`publish_map02_blendg1_witness.py`, which requires the verified
PutPixel/VRAM/DrawOTag bundle and publishes a SHA-256 manifest last.

`tests/test_map02_scoped_blend_stage.py` checks exclusive private
publication, mode bits, JSONL structure, incomplete capture rejection,
symlink rejection, and permissive-directory rejection. The
`DrawOTag` source regression also builds a **separate**
`VH_MAP02_POSIX_STAGE` configuration and checks automatic staging
during a synthetic selected frame.

This stage does **not** provide a corresponding independently
authenticated PutPixel log and does not yet demonstrate a successful
full original-PC-port build or a genuine MAP02 gameplay capture.

## Paired PutPixel + BlendG1 source staging (same closed frame)

`vh_map02_stage_private_pair(private_directory)` supersedes the older
BlendG1-only staging entry point for the generated `DrawOTag` build.
With `VH_MAP02_SCOPED_BLEND_PROBE`, `VH_MAP02_POSIX_STAGE`, and an
explicit nonempty `VH_MAP02_PROBE_OUTPUT_DIR`, the closed native-VRAM
capture is staged as **two files from the same in-memory event array**:

- `putpixel-native-events.pending.jsonl`: every observed native
  PutPixel event in contiguous step order (including opaque and legacy
  blend events)
- `blendg1-native-events.pending.jsonl`: only independently observed
  accurate-mode BlendG1 calls, carrying the originating PutPixel step

Both files have the same frame, selected coordinates and original
DrawOTag primitive provenance. Both are prepared in private 0600
temporary files, flushed, reread byte-for-byte, and installed with
exclusive hard links. If a second link fails, the first newly
published name is rolled back without overwriting either pre-existing
file. The two-file operation is **not a crash-atomic transaction**:
an unclean power loss can leave an orphaned pending file, which is
not trusted and must be recovered manually. The ordinary program
does not emit either log unless explicitly opted in.

The previous `vh_map02_stage_private_blendg1` remains for legacy
diagnostic smoke tests but the current `DrawOTag` generator uses
the paired entry point. The private test suite now covers matching
frame/ordinal/step values and refusal to overwrite either name.

### Strict promotion and final witness validation

Two **separately supplied** pieces of original evidence are required
before any pending files become accepted witness logs:

1. `gpu-putpixel-ot.json` in the private source bundle, containing
   the SHA-256 of the staged PutPixel bytes and independently captured
   DrawOTag/VRAM evidence references. This cannot be generated or
   authenticated from the PutPixel staging file alone.
2. The remaining original source-keyed GTE, DrawOTag and VRAM
   snapshots required by `verify_map02_putpixel_scope.py`.

With those independent private inputs in place, run:

```sh
python3 -m tools.promote_map02_putpixel_stage \
  /private/map02/source-bundle /private/map02/native-capture

python3 -m tools.publish_map02_blendg1_witness \
  /private/map02/source-bundle /private/map02/native-capture

python3 -m tools.verify_map02_blendg1_witness \
  /private/map02/source-bundle /private/map02/native-capture
```

The first program verifies canonical JSONL, strictly bounded numeric
fields, source-frame agreement and the independently supplied
PutPixel SHA-256, publishes `putpixel-native-events.jsonl`
exclusively, and immediately calls the **full** upstream PutPixel
source/VRAM verifier. If verification fails, the newly published file
is removed. It will never manufacture missing OT/VRAM evidence.
The second program independently checks BlendG1 and binds its
published witness to the PutPixel manifest. The third checks the
complete witness chain again.

All directories must already exist with mode 0700 and no symlinks.
This pipeline has not yet been exercised with actual gameplay,
and successful synthetic tests must not be described as physical
PlayStation hardware equivalence.

## What the paired staging stage does *not* establish

`vh_map02_stage_private_pair` has no access to independently sampled
native VRAM snapshots or source-keyed GTE evidence. It writes two
**pending** event logs from the same closed in-memory C sink. They are
internally consistent, but this alone does not prove original gameplay,
complete pixel coverage, independent source provenance, or physical
PS1 blending semantics.

`tools/promote_map02_putpixel_stage.py` is a separate fail-closed
gate. It checks the pre-existing `gpu-putpixel-ot.json` manifest,
requires the staged PutPixel SHA-256 to equal the independently
supplied digest, validates 0..63 contiguous step indices and numeric
bounds, copies the staged bytes into a private no-overwrite final file
and runs the **full** source-keyed
`verify_map02_putpixel_scope.verify_pixel_ot`. Failure removes the
new final file; successfully verifying an arbitrary synthetic fixture
is not sufficient to establish real original game provenance.

`tests/test_map02_paired_publish_chain.py` exercises the entire
Python publication sequence, with the expensive original-GTE/VRAM
verifier deliberately **mocked**. This tests software integration,
hash binding and format compatibility, not game correctness. Together
with the compiled C paired-stage test, it closes the
C JSONL -> PutPixel -> BlendG1 formatting gap. It does **not**
replace actual private source/VRAM witnesses or a native PC-port build.

## 2026-10-17 ordinal correction

The first scoped DrawOTag generator counted **all** non-bucket OT
entries, including `DR_MODE`. The existing independent
`verify_map02_putpixel_scope.py` indexes **only** native VRAM draw
before/after pairs, which exclude DR_MODE. That mismatch could
incorrectly reject real MAP02 events or associate events with the
wrong primitive. The generator now opens/closes and increments
the sink ordinal exclusively for F4, FT4, SPRT and TILE; an
interleaved DR_MODE still updates the original GPU draw state normally,
but cannot create a phantom pixel ordinal. Synthetic regressions
explicitly cover a DR_MODE between two raster draws.
