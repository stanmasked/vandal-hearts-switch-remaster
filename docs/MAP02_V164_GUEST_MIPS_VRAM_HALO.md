# MAP02 v164 — five MIPS-authored GPU rectangles: VRAM deltas and untouched halo

## What this actually proves

This builds on the previously verified **v121** fully self-authored synthetic PS-X EXE, not on original Vandal Hearts game media.

The original v121 interpreter run already executes a CPU-originated six-stage PS1 MIPS program. Stage 0 writes draw-area and mask commands to PS1 GP0 using genuine CPU `SW` instructions. Each of the next five stages writes GP0(60) rectangle packets through **interpreted guest-MIPS instructions**, writes a separate RAM marker, and stops at a source-authored expected PC. The sequence is red → green → blue → cyan → red on a fixed 4×4 tile at X=40..43, Y=160..163.

The v164 opt-in `--vh164-mips-vram-halo` enables that exact existing v121 experiment; **no host-submitted GP0 rectangle words are introduced**. The host only uses `GPU_freeze(1)` to obtain before/after VRAM snapshots.

v164 adds independent verification of the 6×6 halo X=39..44, Y=159..164. A snapshot taken after the MIPS-authored draw setup and before rectangle stage 1 is compared with each of the five later GPU readbacks. The observer requires on *every* stage:

- Exactly 16 inner pixels changed to the current expected 15-bit color.
- Exactly 20 outer pixels remained byte-for-byte unchanged.
- The host then retains the new 6×6 baseline for the next stage.
- The original v121 stage PC, CPU-written RAM marker, Unai handler metrics, five readbacks, 4-back color return, and no-VBlank checks remain mandatory.

The expected native marker is:

`VH164_GUEST_MIPS_UNAI_VRAM_PASS rectangles=5 changed=80 border=100 host_draws=0 original_retail=0`

The negative case changes the synthetic PS-X EXE tag and requires the pre-existing v121 file-authentication refusal `VH121_EXE_REFUSED` (exit 37), with no v164 positive marker. The host-only v163 mode is incompatible with this guest-mode proof and is rejected if mixed with it. Standalone GCC and Clang tests compile the same VRAM halo helper and verify wrong-color, no-change, border-corruption, and missing-baseline refusal.

## What is *not* demonstrated

This is a five-rectangle synthetic MIPS-authored PS1 rendering test using the real pinned PCSX ReARMed/Unai plugin. It is not an original retail MAP02 capture, not a remake gameplay frame, and not Nintendo Switch HD parity. The v158–v162 five-instruction E3 diagnostic also remains a *different* experiment; v164 does not pretend that that fifth E3 state command drew these rectangles.

The EXE is built deterministically from public, independently written source. **No user-owned retail image, confidential trace, or original Vandal Hearts asset is uploaded.** All original assets remain outside public GitHub.
