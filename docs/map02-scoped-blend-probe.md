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
must therefore count **non-bucket primitive entries**, not raw OT walk
steps, when supplying `primitive_ordinal`. It must explicitly bind
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
/* once per non-bucket DrawOTag primitive, in order starting at zero: */
vh_map02_scope_begin_primitive(ordinal);
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
**each non-bucket item in the original OT walker**, including GPU
draw-mode commands. The observer opens the primitive before its switch
dispatch and closes it after. Invalid token resolution or OT cycle
limits abort the capture; a completed target frame is sealed **before**
deferred HD workers begin. No raw pixel data are emitted.

`tests/test_instrument_map02_drawotag_scope.py` uses a synthetic
bucket/primitive chain to check frame binding, non-bucket ordinal
tracking, invalid-token failure, strict opt-in configuration and
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
original `DrawOTag` walker, in addition to the frame, non-bucket ordinal,
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
