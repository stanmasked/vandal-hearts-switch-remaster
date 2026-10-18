# MAP02 v171 — four guest-MIPS phases, exact GP0/GP1 MMIO provenance and 2380 native Unai VRAM samples

This continues proven v170 source-authored layered FT4/E1/E2/E6 native raster
work (63/63 GitHub Actions) by extending the earlier fully self-authored
v77 four-block **synthetic** PS-X EXE to attest the **exact MIPS SW
instruction PC, opcode, port, value and order** for all original GPU
traffic, phase by phase, while preserving the independent v77 native
GPUFreeze pixel and control-register oracle.

Four bounded calls of the original pinned PCSX interpreter's
`ExecuteBlock` execute in **one emulator process**, without resetting
the emulator or replacing the renderer. Guest CPU writes a marker into
RAM at the end of each block; the frontend verifies both marker and
the original MIPS stop PC.

| Phase | GPU GP0 SWs | GP1 SW | GPU state and expected effect |
|---|---:|---|---|
| 0 Setup | 49 | GP1(01) reset FIFO | Upload 4bpp texture and CLUT, draw six blue tiles, program E1 ABR1/E2 window/E6 mask |
| 1 Persist | 7 | none | Textured sprite uses the state from the prior block |
| 2 FIFO reset | 7 | GP1(01) reset FIFO | Preserve E1/E2/E6 and reproduce correct sprite/rectangle pixels |
| 3 Full reset | 9 | GP1(00) full reset | Clear E1/E2/E6, resulting in intentionally different sprite output |

The observer disarms **immediately after each guest CPU block**, before
reading video memory. Then the original separate v77 oracle verifies
**595 exact Unai 15-bit VRAM samples per phase**: six regions of
16 pixels and 499 unchanged neighboring pixels. In all, **2380
samples**, four distinct MIPS stop PCs, four RAM markers and four
sets of E1/E2/E6 control-register expectations must be satisfied.

Actual pinned GCC and Clang native success requires:

`VH171_GUEST_MIPS_MULTIPHASE_VRAM_PASS phases=4 gp0_words=72 gp1_writes=3 samples=2380 pixel_regions=6 fifo_reset_kept=1 full_reset_cleared=1 vblank_asserted=0 original_retail=0`

The stronger negative retains the signed synthetic `VH77SYN!` tag
but changes **one MIPS LUI instruction** in CPU phase 2, replacing
GP1(01) FIFO reset with GP1(00) full reset. The MMIO source observer
must return exit 77 and
`VH171_PHASE_GPU_ORIGIN_REFUSED phase=2` **before** any positive
v171 marker. Independent GCC/Clang fixtures also reject wrong MIPS
PC, instruction opcode, MMIO value, missing GP1, unwanted GP1 in
phase 1 and double arming.

**Strict limits:** A CPU `ExecuteBlock` boundary is *not* a
physical PS1 VBlank. These four test stages and rectangles are
entirely self-authored synthetic assets, not a real Vandal Hearts
MAP02 battle, retail MIPS program, Nintendo Switch output, or HD
graphical parity. No original game media, private source trace
or copyrighted retail artwork is committed to GitHub.
