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
