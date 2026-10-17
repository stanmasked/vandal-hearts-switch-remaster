# MAP02 v122 — MIPS CPU authored RAM → real DMA2 → pinned Unai GPU

Stacked after [v121 Draft PR #112](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/112).

## Separate GPU command transport test

In v121, the emulated PS1 CPU wrote GP0 command words to
`0x1f801810` through interpreted MIPS `SW` instructions. That is
already stronger than the host-submitted v120 control, but it does not
test the PlayStation GPU DMA2 command transport.

v122 adds another **fully synthetic, original, bounded PS-X EXE**.
Stage zero configures GP0 drawing state through interpreted CPU MMIO,
and enables DMA channel 2 by writing `0x00000800` to the PS1 DMA
priority/channel-enable register DPCR at `0x1f8010f0`.
The host calls `GPU_freeze` once to drain previously buffered setup
commands *before enabling the native sample observer*; no new GPU draw
packet is sent by the host.

Each of five subsequent MIPS stages:

1. Writes three 32-bit GP0(60) opaque rectangle words into mapped
   emulated RAM at `0x80012000` via CPU `SW`.
2. Resets the prior CHCR start bit, and programs DMA2 MADR
   (`0x1f8010a0`), BCR (`0x1f8010a4`) and CHCR
   (`0x1f8010a8`) through interpreted CPU stores.
3. Starts the *original pinned PCSX ReARMed* DMA2 RAM→GPU block path
   using `MADR=0x00012000`, `BCR=0x00010003` and
   `CHCR=0x01000201`. In the pinned emulator, `psxDma2`
   invokes `GPU_writeDataMem` for this exact mode.
4. Writes its own unique RAM marker and exits at a precisely bounded
   CPU program counter for the host to verify.

An opt-in, integer-only observer inside the original
`psxDma2` RAM→GPU branch independently counts DMA2 invocations
with exactly these register values, refusing any unexpected invocation.
The host oracle confirms each marker/PC and also verifies all 16
destination pixels using `GPU_freeze` after the respective real
Unai GPU command. The existing v119 native observer must recognize
**exactly five** post-handler observations and **one exact**
A→B→C→D→A return among the 24 selected sample values, all within
the zero-VBlank gap. The previous 24-value buffers are securely
erased afterward.

v122 runs in a separate pinned PCSX process with its own HOME,
after the unchanged v78–v121 workflows. SHA-256 of the original
private v82 event journal is checked before and after the run.
No pixel values, full GPU packets, hashes, source executable or
retail artwork are uploaded — only the aggregate public file
`proof/public/v122-mips-dma2-return-summary.json`.

GCC and Clang test the original MIPS bytecode, DMA channel setup,
CPU-populated packet words and destinations, bounded CPU markers,
strict native status validation, absence of host GPU packet
submission in this run and preservation of the original private
witness. Their full pinned emulator builds separately verify the
actual hardware-emulation DMA2 branch and Unai readback.

## What this cannot establish

v122 is still an *original synthetic test*, not the retail
Vandal Hearts MAP02 GPU command stream. The PS1 DMA2 controller is
emulated, not physical hardware. A return of 24 selected post-handler
16-bit pixels is not whole-VRAM equivalence, hardware GPU completion
timing, actual scanout or Nintendo Switch HD renderer parity.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

All changes stay in a stacked Draft PR; `main` remains untouched.
