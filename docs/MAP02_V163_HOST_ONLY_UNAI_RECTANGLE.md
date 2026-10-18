# MAP02 v163 — opt-in, HOST-submitted Unai VRAM rectangle

This stage is intentionally separate from v158-v162's five source-authored
synthetic MIPS instructions, which end in GP0 E3 (draw-area state only).
That original E3 does not rasterize a rectangle or produce pixels.

The native pinned PCSX ReARMed/Unai emulator now has an **explicit opt-in**
`--vh163-host-unai-rectangle` flag accepted only alongside the existing
source-bound synthetic five-instruction mode and its register witnesses.
Neither retail assets nor private game captures are put into public CI.

After v162 validates and disarms all observers, a *host-authored* seven-word
GPU packet is passed to the real loaded `GPU_writeDataMem` pointer:

- E3 top-left `(0,0)`, E4 bottom-right `(1023,511)`, E5 offset zero,
  E6 mask zero;
- GP0(60) monochrome red variable-size rectangle at X=608, Y=448,
  width=4 and height=4;
- real `GPU_readStatus` drains buffered commands.

Before submitting any new words, the test snapshots the 6x6 VRAM region
X=607..612, Y=447..452 through `GPU_freeze(1)`. Any preexisting red
inner pixel rejects an ambiguous positive. Afterwards it requires exactly
16 changed red 0x001f inner pixels and exactly 20 unchanged border pixels.
An unchanged, extra, clipped, or wrong-color draw is a failure.

Real native smoke success must emit:

`VH163_HOST_ONLY_UNAI_VRAM_RECT_PASS pixels_changed=16 border_unchanged=20 original_retail=0 mips_raster=0`

Negative: invoking the host-only flag without the synthetic five-opcode
provenance must return code 67 and `VH163_INVALID_HOST_MODE_REFUSED` without
emitting the success marker. Both GCC and Clang use the pinned native
emulator as well as a separate C fixture checking baseline rejection,
border tampering, incomplete draw and exact packet shape.

## Boundaries

The rectangle is generated and submitted by a **host C test** after the
five-opcode MIPS witness. It is NOT GP0 traffic produced by the original
retail game, not drawn by that fifth MIPS `SW`, and does NOT demonstrate
actual MAP02 gameplay, full-frame visual parity, Nintendo Switch graphics
or a remade game. Its purpose is a precise emulator GPU raster/VRAM sanity
check on synthetic content, not an authenticated game capture.
