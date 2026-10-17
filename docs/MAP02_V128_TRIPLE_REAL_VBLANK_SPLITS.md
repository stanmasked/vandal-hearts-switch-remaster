# MAP02 v128 — same total of three genuine VBlank edges, four timing splits

Stacked on [Draft PR #118](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/118).

## Question

Does the native Unai sampled VRAM return to A after A-B-C-D-A stay in the
**three-real-VBlank** classification independently of which boundary
between three MIPS-authored DMA2 linked lists carries the wait?

v128 compares four distinct placements, each in its **own actual pinned
PCSX ReARMed process** and **own private HOME**:

| Mode | After DMA1 | After DMA2 | Adjacent handler gaps | Four-back return |
| --- | ---: | ---: | --- | ---: |
| 03 | 0 | 3 | 0,0,3,0 | gap 3 |
| 12 | 1 | 2 | 1,0,2,0 | gap 3 |
| 21 | 2 | 1 | 2,0,1,0 | gap 3 |
| 30 | 3 | 0 | 3,0,0,0 | gap 3 |

The 10,240-byte synthetic EXE differs **only in the eight-byte header
authentication tag** from v127: the MIPS program, three DMA chains,
ten nodes, fifteen GPU packet words and 512-NOP wait pad do not change.
Host control replays PS1 MIPS NOP instructions through the pinned CPU
interpreter. It never injects GPU commands, VBlank callbacks, cycle
counter values, hSync, frame numbers or sampled VRAM.

The native checks demand three separate consecutive real VBlank
callbacks in each process, exactly 3 DMA2 transfers, ten traversed
linked-list nodes, five Unai callbacks and five intermediate VRAM
sample checks. The adjacent native gap-histogram bins and sampled
24-value return classification are independently checked; all unwanted
quintuplet classifications must be zero.

The original v82 private journal SHA-256 is rechecked before and after
every emulator process. The synthetic EXE, log, private pixels, raw
GPU words and hashes are not exported. Only the coarse JSON summary is
published.

## Limits

Real means **emulated** psxRcntUpdate -> GPU_vBlank callbacks, not
physical PS1 scanout. Only the selected 24 x 16-bit VRAM sample values
are compared, not full VRAM. The synthetic EXE is not the retail MAP02.

- original_retail_MAP02_verified = false
- physical_PS1_verified = false
- HD_replacement_approved = false
