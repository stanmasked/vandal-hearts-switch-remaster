# Experimental native-only BlendG1 source observer

Run against a **pristine separate checkout** of upstream
`platform/pc/src/pc_raster.c`:

```sh
python3 -m tools.instrument_map02_blendg1_call \
    /private/upstream/platform/pc/src/pc_raster.c \
    /private/build/pc_raster.blendg1-probe.c
python3 -m unittest tests.test_instrument_map02_blendg1_call
```

Source anchors fail closed if the upstream implementation changes. The
source original is never modified in place. The generator refuses an
existing output file and rejects already instrumented source.

The optional `VH_MAP02_BLENDG1_PROBE` macro enables the hook. By adding
a `nativeTarget` argument to `WritePixel`, the actual accurate-mode
`BlendG1` call emits entry inputs and the returned output only when
the target is native `s_vram`. The HD `s_hires` target still calls
`BlendG1` with no observer. With the macro disabled, ordinary arithmetic
and render paths are unchanged. The private harness must provide:

```c
void vh_map02_blendg1_call(int x, int y, unsigned short fg,
    unsigned short bg, unsigned short result, int abr, int textured);
```

The hook receives **actual** BlendG1 inputs (`fg` already has bit 15
forced high), rather than the original PutPixel `front` argument. The
harness must retain both meanings distinctly. It must also add private
frame, primitive ordinal and PutPixel step from directly observed
DrawOTag context, then use a bounded, non-recursive sink; these values
are not supplied by this source patch.

**Not an authenticated witness yet.** No private sink or frame/ordinal
binding has been integrated in this stage; no actual event stream was
collected. The strict verifier needs complete, independently captured
metadata to compare against PutPixel. In particular, the raw `fg` in
this hook differs from the PutPixel front word when bit 15 was originally
clear; a faithful witness must preserve both. Avoid publishing raw
pixel words and coordinates.

Next: add a private shim that records the original PutPixel front, the
actual BlendG1 fg and bg, output result, DrawOTag frame/ordinal, and step.
Update the verifier schema only when each field is independently
observed and can be authenticated against a native VRAM snapshot.
