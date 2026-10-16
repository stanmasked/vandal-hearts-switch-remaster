# MAP02 v76 — GPU ordering, dynamic CLUT, and E1/E2/E6 state restoration

## Evidence scope

v75 proved 511 out of 511 native 16-bit VRAM samples in the **real pinned
PCSX ReARMed GPU plugin**, using a fully synthetic PS-X EXE executed by the
actual emulated PlayStation MIPS interpreter. The scene tested indexed
STP/ABR, vertical texture windows, and transparency, not original game data.

v76 exercises state changes **between multiple draws**. It uses another
entirely new, self-authored 6144-byte MIPS PS-X EXE, containing no Sony
SDK, commercial PS1 BIOS, Vandal Hearts resources, original texture
images, recorded retail GPU words or commercial game ROMs.

Pinned public emulator:
[PCSX ReARMed 8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).
GPU attributes reference:
[PSX-SPX](https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/).

## True GPU work

The MIPS CPU issues GP1(01), then GP0 drawing-register updates,
three GP0(A0) uploads (4-bit packed texture U0–15, CLUT A at VRAM
X=512 and CLUT B at X=528), and 11 opaque blue 4×4 backdrops.

The texture contains four different indexed lanes:
U0–3 = indexed red with STP=1;
U4–7 = indexed green with STP=1;
U8–11 = indexed red with STP=0;
U12–15 = indexed green with STP=0.

CLUT A has red/green values for index3/4. CLUT B deliberately maps
index3 to cyan. GPU commands then paint these 11 separate areas at
Y128–131. The oracle does **not** derive pixel expectations from the
GPU renderer; BGR555 arithmetic and constants are independently fixed.

| Area X | Operation | Expected 16-bit VRAM |
|---|---|---|
| 40–43 | Blue then semi red then semi green (ABR0) | `0x9DE7` |
| 56–59 | Blue then semi green then semi red (ABR0) | `0x9CEF` |
| 72–75 | Opaque FT4 index3, CLUT A | `0x001F` |
| 88–91 | Identical FT4 index3, switched CLUT B | `0x03FF` |
| 104–107 | GP0(E2) X texture-window remap U4→U12 | `0x03E0` |
| 120–123 | E2 cleared, ordinary U8 index3 lookup | `0x001F` |
| 136–139 | GP0(E6) force mask bit; checking mask blocks green | `0x801F` |
| 152–155 | E6 cleared; green is allowed over previous red | `0x03E0` |
| 168–171 | Raw semi-textured GPU sprite, GP0(E1) ABR0 | `0xBC0F` |
| 184–187 | Same sprite after GP0(E1) ABR1 | `0xFC1F` |
| 200–203 | Same sprite after restoring GP0(E1) ABR0 | `0xBC0F` |

The final three test cells use **raw-textured semi-transparent sprites**
(GP0(67h)) deliberately, instead of textured FT4s: FT4 packets include
their own texture-page field and could override the ambient GP0(E1)
draw-mode ABR setting. A sprite relies on the E1 texture page already
set in GPU state. This makes ABR1 and its restoration observable in
native pixel readback, not just in GP0 command logs.

At the first two cells, changing the draw order produces different
15-bit colors because ABR0 arithmetic is non-commutative across multiple
layers with integer truncation.

## Actual emulator oracle

With opt-in `--vh76-gpu-state-smoke`, the complete native PCSX
ReARMed process:

1. Boots core and HLE without any game or commercial BIOS.
2. Loads the tagged self-authored PS-X EXE, executes the actual MIPS
   interpreter, and verifies an exact RAM completion marker and PC.
3. Verifies observed direct GPU MMIO input and real GPU plugin callbacks.
4. Calls the native original GPU plugin `GPU_freeze(1)` to flush
   commands and read its actual 1024×512 16-bit VRAM.
5. Compares **1162 exact pixels** at X39–204, Y127–133:
   11 × 16 = **176 expected colored pixels** and **986 untouched
   background pixels**. Any mismatch fails closed.

All output reports contain only aggregate counters and remain synthetic.
No real retail GPU capture or game VRAM is sent to GitHub.

## Mandatory native negative tests

Six separate, still-valid synthetic MIPS executables are run inside
the same real PCSX emulator and **must fail pixel comparison**, while
a corrupt EXE identity is rejected separately:

- Reverse the submission order of the first two FT4 semi layers.
- Change the second FT4 from CLUT B to CLUT A.
- Disable GP0(E2) before the windowed FT4.
- Disable GP0(E6) destination mask checking before the protected
  overwrite.
- Keep GP0(E1) ABR0 where ABR1 was requested.
- Fail to restore GP0(E1) ABR0 after drawing the ABR1 sprite.

Both GCC and Clang must build the *complete* pinned emulator, execute
all seven variants and the correct scene, pass new independent Python
tests and rerun the entire inherited v45–v75 original-public-PC-port
GPU/PRS/GTE/OT/VHT1, DMA2, emulated MIPS and privacy regressions.

## Trust boundaries

This only tests one carefully bounded **synthetic GPU software-renderer
scene**, not genuine MAP02 texture ordering, authentic PlayStation
hardware raster parity, native Nintendo Switch GPU parity or HD
texture replacement.

`retail_ps1_pixel_parity_verified=false`
`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

PR must remain a **stacked DRAFT** based on v75 and may not be merged
into `main` as part of this diagnostic stage.
