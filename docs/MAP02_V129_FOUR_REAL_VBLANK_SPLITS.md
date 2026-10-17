# MAP02 v129 — exact upper-bound four genuine VBlank gap splits

Stacked on [v128 Draft PR #119](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/119). Its v126/v127/v128 witnesses remain unchanged.

## Experiment

The original native v116/v119 Unai observer supports gap bins from zero through
four inclusive. The preceding v128 experiment established four distinct
placements of three actual emulator VBlank callbacks. v129 exercises the **upper
supported sampled return gap of four** while keeping the 10,240-byte PS-X EXE
identical except for its 8-byte authentication tag.

| Mode | Real callbacks after DMA1 | Real callbacks after DMA2 | Adjacent Unai handler gaps | Exact sampled A return |
| --- | ---: | ---: | --- | ---: |
| 04 | 0 | 4 | 0,0,4,0 | 4 |
| 13 | 1 | 3 | 1,0,3,0 | 4 |
| 22 | 2 | 2 | 2,0,2,0 | 4 |
| 31 | 3 | 1 | 3,0,1,0 | 4 |
| 40 | 4 | 0 | 4,0,0,0 | 4 |

Every profile runs in its own pinned PCSX ReARMed process and isolated
private HOME directory. The host advances only the existing original
synthetic MIPS CPU NOP/JUMP loop through the interpreter. Genuine
\`psxRcntUpdate -> GPU_vBlank\` callbacks increment the preexisting
emulator observer. CPU cycles, hSync, IRQ, frame numbers, VRAM samples
and GPU command words are never injected.

The native guards require 4 distinct consecutive VBlank callbacks,
3 original MIPS-initiated DMA2 linked lists, 10 actual traversed GPU
nodes, 15 packet words, 5 ordered native Unai post-draw callbacks,
5 intermediate pixel state validations, and independent 0..4 adjacent-gap
histograms with only the single expected four-back return classification.
Failure, missing callback, unexpected callback, duplicate or altered report
must refuse the experiment.

The original private v82 JSONL SHA-256 is checked before and after
each isolated emulator run. Raw private logs, GPU data, EXE, VRAM pixels
and hashes are never public CI artifacts; only a coarse JSON summary
is exported.

## Scope

This is a source-authored synthetic PS1 MIPS program running under a
pinned emulator, **not** the retail MAP02 scene or physical PS1 scanout.
VRAM equality examines 24 selected 16-bit values, not all VRAM.
In particular, successful tests must **not** imply Switch HD parity:

- original_retail_MAP02_verified = false
- physical_PS1_verified = false
- HD_replacement_approved = false
