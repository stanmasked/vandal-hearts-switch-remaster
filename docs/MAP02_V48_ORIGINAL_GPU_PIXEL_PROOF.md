# MAP02 v48 — real GPU per-pixel BGR555/STP and before/after proof

**Verified successful CI:** [GCC and Clang run 38921741802](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38921741802).

## Core result

The original PC-port's source units src/maps/unpack.c, src/core/graphics.c,
platform/pc/src/libgte.c, libgpu.c and pc_raster.c are compiled, linked
and **executed** on synthetic 28x12 PRS map data, with an actual 4bpp VRAM
palette and native/deferred hires render paths.

After existing per-face OT-token provenance v47, the new read-only patch
tools/instrument_map02_v48.py instruments the exact ORIGINAL
pc_raster.c::dda_span around the unchanged PutPixel call.

For sparse, terrain-only samples, stderr logs:
- frame, OT token, GFX/route, render target and scale, x/y and source UV;
- original sampled raw BGR555 texel and draw/skip flag;
- modulation RGB, dither enable, packed BGR555 front color;
- framebuffer pixel before and after PutPixel;
- primitive semi-transparency flag and abr mode.

Native pixels refer to the synchronous v39 token; deferred hires workers
use immutable per-primitive v40/v41 RenderCtx provenance.
Texture-window state, PS1 texture decode, STP, original blend function,
framebuffer pixel write, and original OT order remain unchanged.
Use VH_MAP02_V48_TRACE=1 to activate capture; unset it to disable it.
Capture is skipped if a DDA triangle has an active HD-pack replacement.

## Independent arithmetic validator

tools/verify_map02_pixels_v48.py independently reproduces:
- BGR555 expand, RGB modulation by face-color/128, clamp, pack/truncation;
- all 16 coordinates of the original 4x4 front-color dither matrix;
- transparent 0x0000 texels as framebuffer-preserving skips;
- opaque source when the STP texel bit is clear even if ABE is on;
- STP-gated blends: ABR0 average, ABR1 saturated sum,
  ABR2 saturated subtract, ABR3 sum + 0.25 front;
- the actual after-framebuffer halfword, including preserved mask bit.

It also verifies exact v47 per-face PRS-to-OT provenance. Wrong
frame/token/GFX/route or source PRS face, unsupported v24 mapping,
invalid raw/draw relationship, wrong dithered front color, or altered
after pixel cause a strict refusal. Sparse absence is reported
as insufficient evidence, never a visual disappearance conclusion.

Sample local usage, with inputs from ONE actual instrumented process:

    python3 -m tools.verify_map02_pixels_v48 /private/M_MAP02.PRS \
      /private/map02-gpu-stderr.log --output /private/v48-pixels.json

Add --synthetic-fixture for deliberately synthetic test input only.

## Exactly what CI proved

Workflow: .github/workflows/map02-v48-gpu-pixels.yml
Pinned public upstream: 14552fffa0e0b47e02b57592e274fc6e7a649923

Three synthetic map-11 faces are submitted by the original RenderMapTile:
- frame 1, face (z=8,x=19,face=0), GFX641, v24 local slot241;
- frame 1, face (z=8,x=20,face=0), GFX641, slot241;
- frame 2, face (z=11,x=11,face=0), GFX643, slot243.

The first two share the same GFX, CLUT and UV, yet retain distinct OT
token and per-pixel identities. Actual before/after native and
hires GPU pixel decisions matched independent Python BGR555 arithmetic.
Negative CI modifies the actual logged pixel output and changes a
nonzero raw source texel to zero while draw=1: both are rejected.

| Suite | Passing tests per compiler |
|---|---:|
| v45 bounded PRS regression | 34 |
| v46 source-face correlation | 21 |
| v47 every-face token provenance | 21 |
| v48 independent GPU pixel math | 25 |
| **Total** | **101** |

GCC and Clang both passed the original C decompressor cross-check,
genuine GTE/GPU execution, native-vs-hires OT evidence and framebuffer
identity with one versus two render worker threads.

Artifact names:
- map02-v48-gcc-real-gpu-synthetic
- map02-v48-clang-real-gpu-synthetic

Each stores proof binaries/objects, logs, synthetic input, exact
face/OT and new per-pixel JSON, plus hashes.

## Important limits

**The executed GPU scene uses synthetic OPAQUE texels only.**
STP, transparent skips, 4 ABR blend modes and the full dither matrix
have standalone analytic Python tests, not a demonstrated
all-modes runtime captured game scene.

Pixel arithmetic validation does **not independently re-sample source
VRAM texels/CLUT**. Two different raw texels may quantize to the same
modulated BGR555 output. Thus correct after-PutPixel output does not
by itself prove authentic texture contents or texture-window selection.
This is the primary next validation gate.

The retail M_MAP02.PRS, original game texture pixels, full PC-port
play session and Switch HD-remake executable were not available/run
for this milestone. No HD-replacement is enabled.

All reports keep retail_map_authenticity_proven,
genuine_gameplay_proven, pixel_perfect_visual_fidelity_proven and
HD_replacement_approved equal to false.

Work remains in a stacked draft PR based on v47; main is unchanged.
