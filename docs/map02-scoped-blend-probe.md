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
