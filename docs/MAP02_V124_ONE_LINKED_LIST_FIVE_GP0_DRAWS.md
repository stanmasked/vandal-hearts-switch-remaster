# MAP02 v124 — five ordered GP0 draws in one authentic synthetic MIPS DMA2 list

Stacked after [v123 Draft PR #114](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/114).

## Why another DMA test?

v123 established that the interpreted PS1 MIPS processor could
create and trigger a three-node linked list that contained *one*
GP0 drawing packet, with five distinct linked-list DMA transfers
producing an exact A→B→C→D→A return.

v124 holds the transport fixed at **one** DMA2 linked-list start.
An entirely original MIPS EXE first sets GPU drawing state and
enables DMA2 (stage 0), then writes a full chain to emulated RAM
and triggers *one* CHCR=0x01000401 GPU DMA (stage 1). No GP0 draw
packet or linked-list word is submitted by the host.

The seven linked nodes are:

| Node address | 32-bit header | Meaning |
| --- | --- | --- |
| 0x12000 | 0x00012100 | Empty entry -> 0x12100 |
| 0x12100 | 0x03012200 | Three words, state A, red |
| 0x12200 | 0x03012300 | Three words, state B, green |
| 0x12300 | 0x03012400 | Three words, state C, blue |
| 0x12400 | 0x03012500 | Three words, state D, cyan |
| 0x12500 | 0x03012600 | Three words, state A, red |
| 0x12600 | 0x00800000 | Empty terminator |

MIPS `SW` writes all seven headers and all fifteen GPU words.
An independent aggregate observer in the pinned native
`psxDma2` code confirms exactly one linked-list dispatch.
Another inside `GPUdmaChain` validates **each actual node
traversal** including exact sequence, link targets, word
counts and the zero-word terminating node.

### Independently testing intermediate VRAM

Unlike v123, an external readback **after** the DMA cannot reveal
whether the five intermediate states were rendered in order.
Therefore v124 also instruments the existing original native Unai
post-handler hook, directly after the v115 sample observation.
After **each of the five real draw callbacks**, it checks all
16 pixels in the affected 4×4 VRAM rectangle against the expected
native 16-bit value A, B, C, D or A. Only aggregate success/failure
counts leave the native process; no raw pixel word or hash is
exported. A separate host `GPU_freeze` validates final red pixels.

The existing v119 five-callback observer must report exactly one
four-back return across the 24 selected 16-bit values, with zero
VBlank callbacks, and all four cached prior-value arrays must be
scrubbed at exit. The original v82 private journal and all
v78–v123 experiments are preserved. The v124 program is launched
in its own pinned PCSX process/HOME after prior checks and the
original private journal is verified by SHA-256 both before and
after. Public upload is restricted to
`proof/public/v124-single-dma-five-gp0-summary.json`.

GCC/Clang fast tests validate the MIPS bytecode, exact chain
node source, invariant and refusal counts, native GPU/Unai
hook provenance and private-safe output. Full pinned PCSX runs
also perform the five actual native Unai intermediate pixel
checks for both compilers.

## Limits

This is synthetic MIPS code, **not** actual retail Vandal Hearts
MAP02. It verifies selected post-handler Unai software VRAM
states, not full VRAM equality, physical GPU scanout or
Nintendo Switch HD rendering parity.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The stacked Draft PR leaves `main` unchanged.
