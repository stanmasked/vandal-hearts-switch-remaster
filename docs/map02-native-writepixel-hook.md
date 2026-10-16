# Native MAP02 WritePixel source hook (experimental)

`tools/instrument_map02_native_writepixel.py` applies a strict, bounded
source transformation to a **separate copy** of upstream
`platform/pc/src/pc_raster.c`. Both source anchors must match exactly.
No match, duplicate match, existing instrumentation, or existing output:
**fail closed**.

Usage (from repository root, using a separately checked-out original PC port):

```sh
python3 -m tools.instrument_map02_native_writepixel /path/to/pc_raster.c /tmp/pc_raster.map02-probe.c
python3 -m unittest tests.test_instrument_map02_native_writepixel
```

The generated source compiles as before when
`VH_MAP02_PIXEL_PROBE` is **not** defined. With it defined, linking
requires a private harness implementation:

```c
void vh_map02_native_writepixel(int x, int y,
    unsigned short before, unsigned short front, unsigned short after,
    int abr, int semi, int textured, int accurate);
```

Capture to a private, bounded, coordinate-scoped buffer. Ensure the sink
does not itself call back into the rasterizer. Never commit raw VRAM, color
words, screenshot buffers, coordinates, or trace artifacts to this repository.
The hook runs only after native `s_vram[y][x]` writes; `s_hires` writes are
not observed. Source `front` is the original packed color passed to
`WritePixel`, not an independent re-computation.

**Limitations:** this is a WritePixel *outcome* hook, not a direct BlendG1
entry/exit hook. It does not yet emit frame, primitive ordinal, or PutPixel
step, so its output must NOT be passed off as valid
`blendg1-native-events.jsonl`. A proper harness must provide those markers
using the separately authenticated DrawOTag context, and a separate
BlendG1-specific observer must collect independent entry/exit values.
Do not synthesize a BlendG1 witness from these WritePixel observations.
No actual MAP02 gameplay frame or hardware behavior has been verified.
