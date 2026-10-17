# MAP02 v125 — changing GPU DMA lists with 1+2+2 ordered draws

Stacked after [v124 Draft PR #115](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/115).

## Experiment design

v124 proved that **one** MIPS-started GPU DMA linked list can
deliver five real ordered Unai GP0 rectangles A→B→C→D→A,
including intermediate pixel checks after each native callback.

v125 varies GPU linked-list **start address**, **packet length**
and **number of draw nodes** over three distinct GPU DMA2 starts,
still using an entirely original, synthetic, interpreted MIPS-I
PS-X EXE.

| CPU DMA2 phase | Initial MADR | Linked nodes | GP0 packet words | Draws |
| --- | --- | --- | --- | --- |
| 1 | 0x12000 | 0x12000 → 0x12100 → 0x12200 | 3 | A |
| 2 | 0x13000 | 0x13000 → 0x13100 → 0x13200 | 6 in **one node** | B, C |
| 3 | 0x14000 | 0x14000 → 0x14100 → 0x14200 → 0x14300 | 3 + 3 in **two nodes** | D, A |

Every chain begins with a zero-word entry node and ends in an
`0x00800000` terminator. CPU MIPS instructions write **every
header and GP0 word** into emulated PS1 RAM, then set MADR,
BCR=0 and CHCR=0x01000401 through the emulated DMA2 registers.
The host does not submit draw packets.

Native integer counters in the original pinned
`psxDma2` RAM→GPU linked-list dispatch check MADR values
0x12000, 0x13000 and 0x14000 in exact order. An independent
native `GPUdmaChain` visitor checks the **ten actual node
addresses**, every node's length and next pointer and the
cumulative number of packet words.

For the 6-word node, the original Unai GPU decoder must
execute two complete 3-word GP0 rectangles. The already proven
v124 post-Unai native hook checks all 16 pixels in each
intermediate red/green/blue/cyan/red 4×4 result, and the host
enforces accumulated Unai callback totals **1, 3 and 5**
after the three DMA transfers. Any missing, duplicated or
out-of-order draw must fail the experiment. The v119
24-point exact VRAM observer independently checks a single
four-back return to A with no artificial VBlank.

The host performs one final VRAM `GPU_freeze` readback,
and requires the four private previous sample arrays to
be erased. Original v82 private event journal SHA-256 is
checked before and after a separate opt-in pinned PCSX
process; prior v78–v124 synthetic experiments are preserved.
Public evidence is restricted to
`proof/public/v125-variable-dma-summary.json`, containing only
the aggregate counts, not raw pixels, GPU payloads, game files,
private event trace or screenshot.

Fast GCC/Clang tests inspect the original MIPS bytecode, linked
headers, exact GP0 commands, differing DMA starts, node count,
counter refusals, native hook source and publication privacy.
Full pinned PCSX GCC/Clang runs must additionally execute the
real MIPS interpreter → DMA2 → GPUdmaChain → Unai pipeline.

## Limits

This is a controlled **synthetic** experiment, not retail
Vandal Hearts MAP02. Exact equality refers to only 24
selected 16-bit post-Unai VRAM points, not whole-VRAM parity,
hardware PS1 timing or Nintendo Switch HD rendering.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

Changes remain on a stacked Draft PR. `main` is untouched.
