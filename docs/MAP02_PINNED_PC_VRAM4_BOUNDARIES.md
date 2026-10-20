# MAP02 — pinned PC source versus portable VRAM4 boundaries

This step is part of the **original MAP02 restoration research**, not the
independently authored Switch tactical prototype.

## What the expanded comparison does

`tools/verify_map02_pc_vram4_equivalence.py` extracts the real
`TPageOrigin` and `SampleTexture` function bodies from the **pinned public
PC port** (`HalmyLyseas/VandalHearts-PcPort` commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`, Git blob SHA-1
`ba8a05d161ad778c0b75e452ff0a11ed163c65cd`). Its source-aware
anchor checks refuse modified texture-addressing arithmetic.

A C11 harness compiles those extracted function bodies and the actual
portable `source/map02_vram4_page.h` side-by-side. Both sample a
deterministically generated **synthetic 1024×512-word VRAM image**, with
independently selected page, CLUT and GP0(E2h) texture-window parameters.
Each test covers an entire 256×256-index page, not just selected UV
coordinates.

The original eight cases are retained. Another 24 exercise page x=0/960,
page y=0/256, CLUT x=0/1008 and rows 0/511, offsets 0/31, asymmetric
5-bit texture-window masks, 8-texel boundary crossings and unrelated
tpage high bits. Total **32 × 65,536 = 2,097,152 pixel samples**, for
each GCC and Clang executable.

The test checks the 16-bit BGR555 values returned by the pinned
`SampleTexture` against the values reconstructed from the materialised
4bpp atlas and CLUT. A deliberate portable `effective_u/4` addressing
mutation must fail against the unchanged reference. This negative
control proves the differential test catches at least that concrete
class of wrong portable texel-address calculation rather than just
succeeding on inert data.

## Evidence boundaries

- Does **not** read an original PlayStation game BIN/CUE, EXE, proprietary
  game textures, live GPU VRAM, original MAP02 packets or PS1 hardware.
- Does **not** claim that the public PC port is a cycle-accurate or
  pixel-accurate PS1 GPU implementation.
- Does **not** establish game content parity, original asset conversion,
  depth/order transparency, semi-transparency or actual scene rendering.
- This covers the **4-bpp materialisation path only**; it does not verify
  8-bpp, 15-bpp, blending, raster triangle rules, dithering or
  presentation to Switch.

The dedicated
`.github/workflows/map02-pinned-vram4-boundaries.yml` tests both
GCC and Clang against the same source revision. The inherited
`.github/workflows/map02-upstream-trace.yml` retains its original
pinned-source checkout and now asserts the enlarged pixel count.
Both CI jobs are fully asset-free. Keep the changes Draft and do not
merge them before independent latest-HEAD CI confirmation.
