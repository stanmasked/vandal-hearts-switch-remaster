# MAP02 v172 — actual PCSX VBlank events and source-attested guest MIPS → 2380 Unai VRAM samples

v171 already passed 64/64 GitHub Actions with 4 *bounded CPU interpreter
blocks* (not VBlank frames), independently source-attested 72 GP0 and 3 GP1
native MIPS writes, and four sets of 595 exact real-Unai pixel samples.

v172 uses the pre-existing and independently authored
`VH78SYN!` signed **synthetic** PS-X EXE, an exact binary extension of
the v77 guest four-phase source with an additional 512-NOP MIPS wait pad.
It combines two independently implemented native observers:

1. The actual pinned `psxMemWrite32` MIPS-source observer from v171.
   Before each original interpreter `ExecuteBlock`, arm the exact
   stage-bound GP0/GP1 watch; immediately afterward disarm and require
   exactly 49/7/7/9 GP0 words and, respectively, 1/0/1/1 GP1 writes.
   Check actual MIPS source instruction PC, `SW` opcode, port, data,
   and order against the entirely self-authored guest program.
2. The original v78 read-only counter hook **inside pinned
   `psxRcntUpdate()`**, after its real `GPU_vBlank(1,0)` callback,
   observing four monotonic VBlankStart transitions. The v78 handler
   advances CPU cycles only through bounded **interpreter-executed MIPS
   NOP/jump** blocks, without calling GPU_vBlank from the host or
   forging `psxRegs.cycle`, interrupts or frame counters.

Only after each observed real native PCSX VBlank does the unchanged v78
`GPUFreeze` oracle validate 595 native Unai VRAM pixels, six 4×4
regions and 499 unchanged guard pixels, along with E1/E2/E6 state.
Four separate snapshots total **2380 exact samples** in the same
emulator process.

Expected actual pinned GCC+Clang success:

`VH172_GUEST_MIPS_REAL_VBLANK_VRAM_PASS vblanks=4 phases=4 gp0_words=72 gp1_writes=3 samples=2380 source=psxRcntUpdate console_frame_asserted=0 original_retail=0`

The signed synthetic negative changes only one guest MIPS LUI:
the phase-2 GP1(01) FIFO-reset word becomes GP1(00) full reset,
leaving the synthetic program signature and NOP wait unchanged.
Both native compilers must return exit 78 with
`VH172_MIPS_GP1_VBLANK_ORIGIN_REFUSED phase=2`, never a v172
pixel-positive marker.

**Boundaries:** These are **real events from the emulator's software
psxRcntUpdate / GPU_vBlank path**, not measured video output on a
physical PlayStation or Nintendo Switch. The image is a synthetic
six-rectangle test and all program instructions/texture bytes are
self-authored. Original retail Vandal Hearts MAP02 code, gameplay
screen, real game geometry, physical display timing, GPU hardware
parity, and Switch-HD readiness remain unverified. No user game
media, copyrighted private textures, or private GPU traces
are uploaded to the public repository.
