# MAP02 v170 — guest MIPS layered FT4, CLUT, E1/E2/E6 GPU state and 1162 real Unai pixels

This stage continues the verified v169 synthetic indexed CLUT/STP/ABR/E2
experiment (62/62 workflows) and instruments another **independently
authored synthetic** PS-X executable, v76 `VH76SYN!`. The actual
retail Vandal Hearts executable, MAP02 graphics, textures and private
capture files are not inputs, are not uploaded, and are not claimed.

## Guest MIPS → GPU states → independent VRAM readback

The original self-authored v76 CPU interpreter program writes a genuine
GP1 FIFO-reset command followed by **202 GP0 words**. For each GP0
word, the diagnostic-only v170 native `psxMemWrite32` observer checks
the exact source-generated PC of `SW t1,0(t0)`, opcode, physical GP0
MMIO port, expected data word and order. It does not mutate the CPU,
GPU command queue, timing or VRAM.

The program uploads one 4bpp texture and two separate CLUT palettes via
three GP0(A0) packets, draws 11 blue tile backgrounds and 12
textured FT4 quads, and then 3 GP0(67h) raw textured sprites.
Distinct ordered cases include:

- Swapping red/green semi-transparent FT4 submission order;
- Switching CLUT palettes A and B with identical texture indices;
- Setting and restoring horizontal E2 texture window mapping;
- Enabling E6 force-bit15 and mask-check, then restoring normal writes;
- Using persistent E1 draw mode / ABR0 vs ABR1 for textured sprites,
  followed by resetting the drawing mode.

The original independent v76 pinned Unai `GPU_freeze` oracle
checks **1162 pixels**: 11×16 actual colored pixels in
nonoverlapping rectangles and 986 unchanged surrounding pixels.
It must reject all wrong values before emitting a pass marker.

Expected native GCC and Clang marker:

`VH170_GUEST_MIPS_GPU_STATE_VRAM_PASS gp0_words=202 gp1_words=1 ft4=12 sprites=3 regions=11 pixels_checked=1162 colored=176 guard=986 original_retail=0`

The stricter negative example changes **one MIPS ORI source
instruction**, producing GP0(E6) mask-check-disable
`0xe6000000` in place of required `0xe6000002`. The
self-authored executable signature remains intact. The native source
observer must stop with exit 76 and
`VH170_MIPS_GPU_STATE_REFUSED` *before* crediting any pixels.
Standalone GCC/Clang C fixtures also reject missing GP1 reset,
incorrect MIPS PC/opcode/word and surplus GP0 traffic.

## Limitations

This proves only synthetic guest MIPS commands and native Unai software
rasterizer/state behavior. It does **not** prove actual retail Vandal
Hearts MAP02 polygon geometry, real game command ordering, in-game
screenshot, a Nintendo Switch port or HD-remake parity. No original
retail assets or private source traces are published to GitHub.
