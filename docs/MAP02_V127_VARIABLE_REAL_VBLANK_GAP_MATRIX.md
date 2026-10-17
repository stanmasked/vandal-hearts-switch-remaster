# MAP02 v127 — real emulator VBlank intervals 0 / 1 / 2 between GPU DMA lists

Stacked on [v126 Draft PR #117](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/117).

## Objective

The original synthetic PS1 MIPS CPU already authors three variable GPU
linked-list DMA2 transfers A | B,C | D,A, with five actual Unai draw
callbacks and intermediate VRAM value checks. v126 advanced the
interpreted CPU until exactly one **real** pinned PCSX ReARMed
`psxRcntUpdate` → `GPU_vBlank(1,0)` callback between each consecutive
DMA transfer, proving the exact sampled A-B-C-D-A return in VBlank
gap 2.

v127 holds the **MIPS CPU, GP0 command packets, GPU node lists,
native Unai renderer, and 512-NOP wait bytecode identical to v126**.
The only change to the self-authored PS-X EXE is its eight-byte
authentication tag, `VH127SY!`. Host control chooses *when* to
resume the existing MIPS NOP wait pad, never writing PS1 CPU cycle
counters, GPU VBlank callbacks, frame numbers, sample metrics,
GPU payloads or IRQ state.

In four **separate emulator processes** and with distinct private
HOME directories, the host requests the following exact numbers
of *genuine* VBlank edges after DMA1 and after DMA2:

| Mode | Edges after DMA1 | Edges after DMA2 | Consecutive Unai gaps | Five-handler A return gap |
|---|---:|---:|---|---:|
| 00 | 0 | 0 | 0,0,0,0 | 0 |
| 11 | 1 | 1 | 1,0,1,0 | 2 |
| 02 | 0 | 2 | 0,0,2,0 | 2 |
| 20 | 2 | 0 | 2,0,0,0 | 2 |

A zero interval uses **no** MIPS wait instruction. An interval of
one or two requires one or two separately observed, incrementally
bounded `GPU_vBlank` callbacks. Each accepted event must advance
the observed counter by *exactly one*, have an actual later CPU cycle
and nonzero hSync observation, and retain consecutive frame numbers
relative to earlier accepted events in that run. Each awaited edge
is bounded to 8,000 512-NOP interpreter blocks; missing or
unexpected extra events cause a fail-closed refusal.

The native v115 sidecar checks the aggregate VBlank count after each
boundary. Independent v116 adjacent-gap histograms must be
exactly 4/0/0, 2/2/0, 3/0/1, or 3/0/1 for gaps 0/1/2.
The native v119 quintuplet observer must separately confirm a single
exact sampled 24-value return to A in gap 0 or gap 2, with all
other four-back classifications rejected.

The original v124 native hook still checks **16 real software VRAM
pixels after each A, B, C, D and A Unai callback**, and v125 native
transport witnesses still require exactly three MIPS-started DMA
transfers, ten traversed GPU list nodes and fifteen words.

The published original v82 private JSONL is SHA-256 validated
**before and after every one of the four separate emulator runs**,
and no private journal, raw GPU word, private pixel sample,
screenshot, synthetic EXE or hash is uploaded. The only public
artifact is aggregate-only
`proof/public/v127-real-vblank-profiles-summary.json`.
GCC and Clang test original bytecode identity, VBlank source,
four precise classifications, counter error refusal and private
report restrictions before the pinned full host emulator matrix.

## Scope and limits

These are real **emulator** VBlank callbacks, not physical PS1 GPU
timing or proof that a frame was displayed. The same 24 selected
16-bit post-Unai VRAM points are compared, not the full VRAM.
The synthetic EXE is not a retail Vandal Hearts MAP02 instruction
stream, and this does not authorize Nintendo Switch HD parity.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The stacked PR remains Draft. `main` is untouched.
