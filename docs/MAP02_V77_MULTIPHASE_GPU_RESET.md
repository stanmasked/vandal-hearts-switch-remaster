# MAP02 v77 — multiple MIPS CPU blocks, persistent GPU state, GP1 FIFO versus full reset

## Purpose

Stages v70–v76 established actual **native PCSX ReARMed software-GPU VRAM**
readback and independent pixel comparisons for entirely synthetic
PlayStation MIPS programs. Their previous verification used one bounded
CPU block and one VRAM readback per process.

v77 verifies **state persistence across four separately executed CPU
blocks inside the same running emulator process**, with a VRAM snapshot
between every block. It distinguishes the PS1 GPU **GP1(01) FIFO reset**
from **GP1(00) full GPU reset**, checks the saved GP0(E1/E2/E6) GPU
registers and preserves the already rasterized contents of VRAM.

These are **logical CPU/GPU phase boundaries**, NOT observed PS1 vertical
blanking events, real video frames, authentic retail scene transitions,
or Nintendo Switch rendering. The test never loads a Vandal Hearts
game image, PS1 commercial BIOS, Sony SDK or original game assets.

Pinned public emulator source:
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

### Program structure and checkpoints

The self-authored **6,144-byte PS-X EXE** contains four MIPS-I code
segments inside its 4 KiB load section. Each segment writes a unique
completion marker to CPU RAM and performs one unconditional MIPS jump;
a single `psxCpu->ExecuteBlock` call stops after each branch. The native
frontend repeats the call exactly four times, verifying each next PC
and RAM marker, *without* a SysReset, re-loading the EXE, recreating
the GPU plugin, or shutting down the process between steps.

The four logical phases are:

1. **Setup:** GP1(01) reset command FIFO, upload hand-authored 4bpp
   indexed texels (U4..7 green with STP1, U12..15 red with STP1),
   upload 16-entry CLUT, draw six blue 4×4 backdrops; finally set
   E1=ABR1, E2 horizontal window U4→U12, E6=set destination-mask bit.
   A native `GPU_freeze(1)` verifies blue pixels and all three
   command-state registers.
2. **Carry state:** without any E1/E2/E6 writes, draw a raw
   semi-textured sprite at X40, sampling red through E2 and adding
   it to blue via E1/ABR1, and an opaque red rectangle at X56 whose
   bit15 is forced by E6. Native expected outputs are
   `0xFC1F` and `0x801F`.
3. **FIFO-only reset:** GP1(01) is submitted **between** the preceding
   pixel snapshot and these new GP0 draws. Without reprogramming
   E1/E2/E6, draw the same operations at X72/X88. Pixel colors must
   remain `0xFC1F` and `0x801F`. Observed GPU register readback
   must retain E1/E2/E6 exactly.
4. **Full GPU reset:** GP1(00) resets GPU command state, then only
   the drawing-area bounds GP0(E3/E4) are re-established (these
   limits themselves are not the tested attributes). The same
   sprite and rectangle are drawn at X104/X120 without restoring
   E1/E2/E6. Now U4 indexes **green** without E2, the E1 default
   blending mode is **ABR0** instead of ABR1, and E6 no longer
   forces bit15. Required pixels become `0xBDE0` and `0x001F`.
   Previously drawn pixels and the original texture/CLUT must
   remain in VRAM.

### Independent pixel oracle

At each checkpoint, the genuine source-built emulator GPU plugin
`GPU_freeze(SAVE=1)` flushes buffered GPU commands and returns the
actual 1024×512 native BGR555 VRAM pointer. A **source-independent**
fixed C oracle compares x=39..123 and y=159..165, 85×7=**595**
pixels per checkpoint: 96 in six rectangles and 499 surrounding
untouched pixels.

This totals **4×595 = 2,380 separate pixel comparisons**, with
four sets of six expected colors. In addition, each checkpoint
compares `GPUFreeze_t.ulControl[0xe1/0xe2/0xe6]` to the exact
expected GPU E1/E2/E6 register values. The oracle verifies pixels
*before* comparing the frozen registers; a false positive callback
or fake GPU trace cannot pass.

### Negative real-emulator evidence

The workflow executes six different, valid-marker synthetic MIPS
EXEs that change actual GPU words **without changing the CPU
completion markers**:

- Change phase 3 GP1(01) FIFO-only reset to GP1(00) full reset.
- Change phase 4 GP1(00) full reset to GP1(01) FIFO-only reset.
- Disable persistent E1 ABR1 setup.
- Disable persistent E2 U-window remapping.
- Disable E6 destination-mask bit forcing.
- Alter the final-phase raw red rectangle command to green.

Each mutation must reach native VRAM comparison and be rejected for
a pixel mismatch. A changed EXE marker is refused separately, without
claiming it is cryptographic hardware authentication.

The CI contains **37 new v77 Python tests**, two full GCC+Clang native
PCSX emulator builds, all v45–v76 original-public-PC-port
GPU/PRS/GTE/OT/VHT1/DMA/PS1 CPU/provenance regressions, and the four
actual MIPS phase checkpoints for every compiler. Only synthetic
CPU/GPU logs and aggregate proofs are uploaded; never upload private
original-game captures, retail VRAM or licensed textures.

## Evidence limits

Neither a bounded `ExecuteBlock` boundary nor GPUfreeze snapshot
constitutes a real PS1 video `VBlank` event. We have not yet verified
hardware frame timing, retail MAP02 scene transitions or original
physical GPU behavior. Even four successful native PCSX synthetic
checkpoints **do not authorize Nintendo Switch HD texture replacement**.

- `physical_gpu_vblank_boundaries_observed=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

The v77 PR remains **DRAFT**, stacked over v76; this milestone does
not merge or otherwise modify `main`.
