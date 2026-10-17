# MAP02 v126 — genuine emulator VBlank between CPU-created GPU DMA lists

Stacked after [v125 Draft PR #116](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/116).

## Aim

v125 proved three consecutive MIPS-initiated DMA2 linked lists that
deliver five ordered actual Unai GPU rectangles A→B→C→D→A. All
five sample callbacks happened within a zero-VBlank interval, and
the exact sampled-value return was necessarily classified into gap 0.

v126 keeps those identical **CPU-authored** three lists, addresses,
headers, payloads, and native pixel checks, but advances the emulated
PlayStation CPU by executing an original **512 NOP + self-jump MIPS
wait pad** between the first and second DMA and between the second
and third DMA.

The host resumes the synthetic MIPS program only after the pinned
PCSX ReARMed **original `psxRcntUpdate()` code** has actually
invoked `GPU_vBlank(1,0)` once. The v78 read-only observer records
the real callback's cycle, frame and hSync metadata. The test checks
a strictly increasing CPU cycle and consecutive actual emulator
frames, with bounded 8,000 wait-pad iterations.

The test NEVER manually invokes a VBlank callback, writes
`psxRegs.cycle`, modifies hSync or fabricated IRQs, mutates
the VBlank counter, or alters the original GPU callback path.

## Observed expectations

The five intermediate native Unai draw observations are still

| Draw | DMA2 list | Previously observed emulator VBlank edges |
| --- | --- | --- |
| A | 0x12000 (one GP0 command) | 0 |
| B | 0x13000 (first GP0 command in a 6-word node) | 1 |
| C | 0x13000 (second command in that same node) | 1 |
| D | 0x14000 (first 3-word node) | 2 |
| A | 0x14000 (second 3-word node) | 2 |

Adjacent callback VBlank gaps must be **1, 0, 1, 0**.
After both waits the native v115 metrics must report the correct
actual VBlank count and unchanged Unai handler total for that point.
The v116 independent gap histogram must show exactly two pairs in
gap 0, two pairs in gap 1 and none elsewhere.

The existing **native v119** exact 24-point sampled-value comparison
must report a single return to four callbacks earlier in **gap 2**,
not gap 0, with zero classifications in competing return bins.
Native per-draw 16-pixel checks continue to enforce A-B-C-D-A
and protect against any out-of-order or skipped GPU command.

Three actual GPU linked-list DMA starts, ten visited nodes and 15
GPU words are still validated in the original
`psxDma2` / `GPUdmaChain` code. The test is run as a separate
original synthetic PS-X EXE and isolated emulator process with a
dedicated HOME; the original published v82 private event journal is
SHA-256 checked before and after this run.

Only the aggregate public report
`proof/public/v126-genuine-vblank-dma-summary.json` may be
uploaded; never full VRAM, GPU words, screenshots, program bytes
or any private journal.

## Limits

All events belong to the pinned **software emulator** and an
original, **synthetic** MIPS program. The VBlank events are genuine
PCSX ReARMed callback observations, **not physical PlayStation GPU
timing, scanout or completed PS1 frames**. Equality only covers 24
selected 16-bit post-Unai VRAM positions.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

Changes stay in a stacked Draft PR. `main` is untouched.
