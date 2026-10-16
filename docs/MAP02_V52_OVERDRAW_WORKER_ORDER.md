# Map 02 v52 — original GPU multi-layer overdraw, order and 1/2/4 HD-worker reproducibility

**Scope:** Execute the pinned public PC-port's ORIGINAL
`FillQuad → FillTriangleDDA → SampleTexture → PutPixel` against an
ordered sequence of *overlapping* synthetic texture-mapped polygons,
including four different hardware ABR modes, source STP, transparent
texels, texture-depth changes, GP0 texture-window changes and dithering.

**Public upstream:** `HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.

**GitHub Actions:** `.github/workflows/map02-v52-overdraw-order.yml`,
with independent GCC and Clang builds of the actual original PC-port C.

## What the new C harness actually runs

`tests/map02_v52_overdraw_gpu.c` constructs **five** distinct
synthetic scenes. Each consists of **five** completely overlapping
FT4-like textured quads using 4bpp indexed, 8bpp indexed or 15bpp
direct synthetic VRAM data and CLUT rows. The five scenes are:

- **mixed_stp**: opaque red followed by STP-controlled ABR0 and ABR1
  source layers, an entirely transparent texel, then a subtractive
  ABR2 layer.
- **mixed_reversed**: precisely the same five input layers but
  submitted in **reverse order**. The expected final BGR555 color must
  be different, independently proving that order is not lost.
- **abr_chain**: consecutive original GPU ABR0, ABR1, ABR2 and ABR3
  operations, each consuming the previous layer's framebuffer output.
- **window_interleave**: distinct 4-, 8-, 15-bit source palettes and
  GP0 X/Y texture-window masks and offsets, including zero texels.
- **dither_overdraw**: overlapping STP, ABR and transparent sources
  with original ordered dithering enabled.

The C fixture checks packed texture source-word addresses for accidental
aliasing, clears and mirrors the same BGR555 background before each run,
and executes each ordered sequence via:

1. Native `RenderCtx.target=0` (original native VRAM).
2. Direct `RenderCtx.target=1,scale=2` (actual 2× hi-res memory).
3. Production `HiresAppendQuad → HiresRasterizeThreaded`, with a
   **separate, immutable RenderCtx snapshot for each layer** and 64
   non-overlapping filler rectangles to force real worker threads
   rather than a small-display-list fallback.

Each test process sets `VH_ACCURATE=1`, `VH_INTERNAL_SCALE=2`,
and takes `VH_RASTER_THREADS` from **the CI runner**, not from a fake
worker count in the C harness. Separate processes run with 1, 2 and
4 workers, avoiding reuse of cached thread-count settings.

The original GPU functions are unchanged by v52.

## Stronger full-area and thread-band proof

The textured quad spans source-space x=80..96 and **y=40..200**, hence
its real 2× hi-res covered region is **32×320 = 10,240 output pixels**.
For the 4-worker division of clip range y=0..240, this quad spans
**all four bands**: 0–59, 60–119, 120–179 and 180–239. For the
2-worker division it spans both bands.

The harness compares each of those **10,240 pixels byte-for-byte**
between direct hi-res and deferred multiworker hi-res for every
scenario and worker count. It also records the full-region FNV64
fingerprint for independent cross-run verification.

With five scenes and three worker settings, that is **153,600
hi-res halfword comparisons per compiler**, in addition to
individual pixel and source-word assertions. The independent
Python reference checks the native and HD colors across seven
explicit probe rows **55, 60, 119, 120, 179, 180 and 190**, including
the exact thread-band boundaries. These observations come from real
rasterizer output, not an estimated or redrawn image.

## Independent fail-closed reference

`tools/verify_map02_overdraw_v52.py` contains an **immutable independent
manifest** defining the five scenes' source colors, texture-window
settings, formats, texture indices and precise drawing order.
It checks actual C records against this manifest before computing
the final color through the independent prior Python v48 BGR555/STP/ABR
reference.

For every scene and each of the native and hi-res sample coordinates,
the reference independently replays all five layers in their
original order. A zero texel leaves the prior framebuffer halfword
intact; only polygon ABE **together with source STP** invokes
one of the four 5-bit ABR formulas; normal opaque writes overwrite
earlier layers. A separate v49 oracle verifies true texture
word/CLUT/texture-window addressing on every original C layer record.

The reference also requires all five scenes, the correct 25
source layers, positive evidence for all four ABR modes and transparent
texels, correct source and window parameters, correct 1/2/4-worker
settings, and identical hi-res surface hashes and per-row pixels.
Cross-worker differences fail the audit.

Intentional modifications to genuine C execution logs — wrong
composited pixel, source word, layer order, CLUT/window or
full-area fingerprint — must yield a nonzero verifier exit code.

## CI regression and artifacts

The workflow preserves earlier v45–v51 tests and the original
synthetic PRS → `RenderMapTile` → GTE → GPU provenance chain, then
builds/executes the new standalone real rasterizer scene matrix.

| Python suite | Tests per compiler |
|---|---:|
| v45 safe bounded PRS | 34 |
| v46 face identity | 21 |
| v47 terrain face-to-OT | 21 |
| v48 pixel STP / ABR | 25 |
| v49 VRAM / CLUT | 28 |
| v50 native raster modes | 15 |
| v51 hi-res 2-worker modes | 13 |
| v52 layered source/order/worker checks | 24 |
| **Total** | **181** |

The new real C harness is tested separately in **GCC and Clang**,
and uploads its executable, original output logs for each
worker setting and JSON summary in the
`map02-v52-<compiler>-real-gpu-synthetic` artifact.

### Limitations / exact claim boundary

This is a **standalone synthetic input** feeding the original
`FillQuad` rasterizer and its genuine production deferred
multiworker rasterization scheduler. It is **not** a full
`DrawOTag` traversal of a real multi-polygon retail-game frame.
The inherited v45–v51 CI covers authentic *source code* for the
terrain producer/GTE/OT provenance, also on synthetic models, but
not on the user's original PS1 disc data.

- No original `M_MAP02.PRS`, artwork, original retail VRAM snapshot,
  PS1 screenshot or full playable Vandal Hearts game was used.
- No HD texture assets have been generated/injected or approved.
- Full-screen overdraw/geometry edges, interleaved original OT
  primitive kinds, masked destination writes and real retail frame
  fidelity remain separate future validation gates.
- The JSON always sets `HD_replacement_approved=false` and
  `original_map_gameplay_proven=false`.

The work is an **unmerged stacked draft PR #27**, based on v51,
and does not modify `main`. A later step should validate actual
OT ordering and more mixed primitive kinds in native and hi-res
frame captures when legally held original resources become available.
