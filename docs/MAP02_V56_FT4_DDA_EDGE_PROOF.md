# MAP02 v56 — original FT4 DDA shared diagonals, clipping, STP

## Real source code under test

Pinned public PC-port:
HalmyLyseas/VandalHearts-PcPort revision
14552fffa0e0b47e02b57592e274fc6e7a649923.

Original ClearOTag → AddPrim → DrawOTag → FillQuad →
two FillTriangleDDA functions are genuinely compiled, linked and
run in native VRAM and the production deferred 2x renderer at
VH_RASTER_THREADS=1, 2 and 4. The only inputs are SYNTHETIC
test-owned geometry, background colors, texture halfwords and OT
packets. No original game data is included.

## Test cases and independent boundaries

Nine real original GPU scenarios:
- Four STP-enabled semi-transparent FT4s, ABR 0/1/2/3.
- An ABE-enabled polygon with STP clear: opaque overwrite.
- Zero transparent texel: background preserved.
- Half-open clipped FT4, from 20×20 polygon down to 10×12.
- Destination halfword with bit15 already set (known unsupported
  PS1 destination-mask hardware condition, explained below).
- One skewed quad: direct-vs-deferred original-C comparison ONLY;
  independent exact skewed-edge coverage is NOT yet proven.

Eight non-skew axis-aligned cases independently specify the
entire 48×48 native and 96×96 actual HD BGR555 framebuffer,
including all pixels on the FT4 internal triangle seam and
clipped/shared polygon boundaries. Expected color comes from
an INDEPENDENT Python modulate/STP/ABR/half-open geometry
oracle, not original C raster functions.

C also performs a separate original FillQuad pass after
resetting its target and compares all 9,216 hi-res pixels
byte-for-byte with actual DrawOTag deferred output.

Per compiler, 9 cases × 3 worker counts × 9,216 =
248,832 actual original-C hi-res pixel comparisons.
Independent full-image Python oracle:
8 cases × 3 workers × 2,304 native pixels =
55,296 native halfwords, and
8 × 3 × 9,216 hi-res pixels = 221,184 hi-res halfwords.

The skewed original GPU case is deliberately marked as
original-C direct/deferred-only and cannot be used to
claim independent hardware rasterizer edge parity.

## PS1 destination-mask warning

The original PC-port WritePixel in the pinned source has
source texture STP bit15 and four ABR modes, BUT DOES NOT
implement the independent original PS1 GP0(E6) destination
mask-bit write protection. A destination value 0x8010
is overwritten by an opaque 0x03e0 source pixel; this
describes current port behavior and is not a PS1 hardware
fidelity success.

The independent proof explicitly outputs:
- mask_destination_test_implemented_in_original_PC_port=false
- mask_destination_test_hardware_parity_proven=false
- original_retail_MAP02_verified=false
- HD_replacement_approved=false

No production mask-state, original GPU file or HD replacement
path is changed by this milestone.

## Code and CI

- tests/map02_v56_triangle_seams.c
- tools/verify_map02_triangle_seams_v56.py
- tests/test_map02_triangle_seams_v56.py
- .github/workflows/map02-v56-triangle-edges.yml

GCC + Clang matrix retains the previous v45-v55 bounded PRS,
terrain face, OT, original-GPU DDA, CLUT, indexed texture, native/
deferred-HD, 1/2/4-worker and 256-packet ordering provenance.
The new verifier rejects actual altered original-C sample colors,
source/clip metadata, transparent color decisions, full
framebuffer hashes and cross-worker disagreements.

The compiled source and full execution artifacts are
available from the successful GitHub Actions run when
confirmed. This file does not claim success before CI.

## Limitations

This test does not validate authentic retail M_MAP02.PRS,
disc art, real-game source GPU input, original PS1
screenshots, Nintendo Switch gameplay or HD texture
replacements. The production destination mask behavior
is a separate unresolved engine fidelity gap.

Changes are in stacked draft PR #36, based on #34;
nothing is merged into main.
