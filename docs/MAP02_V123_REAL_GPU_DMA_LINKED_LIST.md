# MAP02 v123 — CPU-authored GPU DMA2 linked-list traversal inside pinned PCSX

Stacked after [v122 Draft PR #113](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/113).

## Motivation and design

v122 proved that an original interpreted synthetic MIPS CPU creates
GP0(60) rectangle command words in PlayStation RAM and starts the
emulated channel-2 RAM→GPU block DMA transfer. v123 exercises the
distinct PlayStation DMA2 **linked-list** mode `CHCR=0x01000401`
and the pinned PCSX ReARMed `GPU_dmaChain` parser.

Each of five MIPS draw stages writes **three linked-list nodes** into
emulated RAM via actual CPU `SW` instructions:

- Node at `0x00012000`: header `0x00012100`. Zero GP0 words; link
  to the next node.
- Node at `0x00012100`: header `0x03012200`. Exactly three
  GPU words form a GP0(60) 4×4 opaque rectangle at x=40, y=160.
  Link to the final node.
- Node at `0x00012200`: header `0x00800000`. Zero words, with
  bit 23 set as the linked-list terminator.

The three-node list contains **exactly one actual draw packet**. Empty
head/tail nodes exercise genuine pointer traversal while preserving
the established five-observation A→B→C→D→A exact-value test. Header
and command words are created by interpreted MIPS, not written into
RAM by the host. All five stages write DMA2 MADR `0x00012000`,
BCR `0` (unused for linked-list mode), and CHCR `0x01000401`,
after channel 2 was enabled via DPCR by MIPS at setup stage zero.

Test-only integer counters are placed at the original pinned
`psxDma2` linked-list dispatch and, separately, **inside
`GPUdmaChain` at each node traversal**. They check the expected
per-node addresses, word counts and next pointers, refusing
unexpected nodes or loops. The five transfers must produce 15
visited linked-list nodes and 15 total GP0 words, with no invalid
transport events.

The established v119 native Unai 24-point exact-value observer
must independently record five post-handler draws and **one**
return to the first post-handler sample after A→B→C→D→A,
with no extra VBlank callbacks. The pinned host separately reads
all 16 pixels in each actual 4×4 rectangle via `GPU_freeze`;
the exact 24-point cached samples are scrubbed afterward.

v123 executes in its own opt-in PCSX process and private HOME,
after the already proven v78–v122 controls. The previous
canonical v82 private journal is verified by SHA-256 before and
after this process. No image, pixel word, GPU payload, whole-VRAM
dump, executable, or private journal is publicly uploaded:
only aggregate counts in
`proof/public/v123-mips-gpu-linked-list-summary.json`.

The new GCC/Clang tests verify the six bounded MIPS stages,
all RAM-authored node header words, GPU packet words, native
linked-list dispatch and traversal hooks, expected count totals,
refusal of forged status, preservation of the previous v122
workflow, and aggregate-only publication.

## Limits

This is an original synthetic program inside a pinned emulator,
not the original retail Vandal Hearts MAP02 or physical PS1 GPU.
The 24 selected 16-bit VRAM points cannot prove whole VRAM
persistence, hardware timing, scanout, or Nintendo Switch HD parity.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

The stacked Draft PR does not modify `main`.
