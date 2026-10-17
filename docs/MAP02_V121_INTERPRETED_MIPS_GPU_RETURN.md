# MAP02 v121 — actual interpreted-MIPS-authored GP0 return inside PCSX Unai

Stacked after [v120 Draft PR #111](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/111).

## Objective

v120 demonstrated an A→B→C→D→A exact sampled-value return inside
the **real pinned PCSX ReARMed Unai renderer**, but all five colored
GP0 rectangles were **submitted by the host** with
`GPU_writeDataMem`, after the original private MAP02 synthetic
journal had been published. That is a valid renderer test, **not**
evidence that the PlayStation MIPS interpreter delivered them.

v121 creates a second, entirely self-authored and bounded
`VH121SY!`-tagged PS-X EXE. Its hand-encoded MIPS instructions
write words to the PS1 GP0 MMIO port (`0x1f801810`) via CPU
`SW` instructions. Six bounded stages execute inside the same
pinned host emulator process:

1. MIPS-authored GPU draw-area, mask, texture-page/window and offset
   setup commands.
2. MIPS-authored flat red 4×4 GP0(60) rectangle (state A).
3. Green 4×4 rectangle (state B).
4. Blue 4×4 rectangle (state C).
5. Yellow/cyan 4×4 rectangle (state D).
6. The original red rectangle (state A).

The host calls the real CPU interpreter's `ExecuteBlock` once per
stage, and verifies both the new MIPS-authored marker written into
PS1 RAM and the expected destination PC. The GPU commands themselves
are **not** submitted by the host.

Stage zero is outside the equality witness. Since CPU MMIO
`GPUwriteData` buffers GP0 words in the real GPU plugin, the host first
calls `GPU_freeze` to flush already CPU-authored setup commands. This
adds **no host-authored GPU command**. Only after that drain does the host
reset the **private observer**, enable the established 24-point native
Unai readback, and allow five actual CPU-authored rectangle draws. Each is verified by a `GPU_freeze` readback of
all 16 destination pixels, against expected 16-bit colors. The
existing native v119 equality observer must report exactly five
handlers and precisely one return to four callbacks earlier, in
the zero-VBlank gap class, with no other classifications. Reset
must securely erase all four old 24-value buffers.

The new EXE uses the native renderer of pinned PCSX ReARMed, not a
stand-in software model. It is launched as a **separate emulator
process with its own HOME**, after the full original v104/v120 smoke,
including its private v82 event journal and duplicate-target
protection checks. A before-and-after `sha256sum -c` binds the
original private journal across the new run. The new run has no
private export destination set, and never publishes raw game,
GPU, VRAM or pixel contents. Only the aggregate JSON
`proof/public/v121-mips-gp0-return-summary.json` is uploaded.

The original v78 synthetic EXE builder, v82 JSONL event schema,
v120 host-submitted control, old flags, and v115–v119 native
observer ABI remain unmodified. GCC and Clang test the original
MIPS bytecode, bounded branch targets, authentic GP0 `SW` words,
CPU markers, absence of host-GP0 calls from the v121 oracle,
fail-closed marker checking and source/runner privacy constraints.
The full pinned CI compiles Unai and executes both MIPS and host
synthetic controls under GCC and Clang.

## Limitations

This is a **fully synthetic** PlayStation program, not retail
Vandal Hearts MAP02 or a captured sequence of original GP0
commands. The five state comparisons concern only 24 selected
16-bit VRAM locations immediately after observed Unai callbacks.
The test does not establish PS1 physical GPU timing, hardware
scanout, whole-VRAM equivalence, or HD parity on Nintendo Switch.

`original_retail_MAP02_verified=false`
`physical_PS1_verified=false`
`HD_replacement_approved=false`

Changes remain in a stacked Draft PR; `main` is untouched.
