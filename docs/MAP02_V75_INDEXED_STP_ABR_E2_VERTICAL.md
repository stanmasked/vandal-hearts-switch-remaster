# MAP02 v75 — indexed CLUT STP/ABR and vertical GP0(E2) pixel verification

## Context and provenance

The completed v74 milestone proved **399 exact native VRAM pixels** from
an entirely synthetic MIPS PlayStation executable, exercising 4bpp/8bpp
indexed texture lookup, two CLUT palettes, horizontal E2 texture windows
and zero-index transparency in a pinned *software* PCSX ReARMed GPU plugin.

v75 tests more interaction among GPU state fields rather than claiming
anything about real Vandal Hearts data. The source executable is **6144
bytes created from hand-written MIPS-I opcodes** using Python, with no
retail game textures, Sony SDK, commercial BIOS or private captures.

The pinned emulator is
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

## Native PS1 GPU workload

The emulated MIPS CPU resets the GPU FIFO through GP1(01) and issues
real 32-bit GP0 writes through address `0x1f801810`. It uploads:

- 4bpp packed indices, 2 VRAM halfwords × 12 rows at VRAM (0,0);
  U0..3 index 1, U4..7 index 2, with V8..11/U0..3 index 3.
- 8bpp packed indices, 4 halfwords × 4 rows at VRAM (64,0):
  U0..3 palette index 17 and U4..7 palette index zero.
- 16 CLUT halfwords at (512,0), including 4bpp index1
  `0x801f` (red + STP bit), index2 `0x03e0` (green with
  STP bit clear), index3 `0x03ff` (cyan).
- 256 CLUT halfwords at (528,0), including index17
  `0x801f` and transparent zero index.

Five blue 4×4 backdrops are painted at VRAM X=40,56,72,88,104,
Y=104. Then five FT4 commands sample the indexed textures:

| Test area | PS1 texture interaction | Independent BGR555 expectation |
|---|---|---|
| X 40–43 | 4bpp CLUT, STP=1, semi FT4, ABR0 average | `0xBC0F` |
| X 56–59 | 4bpp CLUT, STP=0, same semi FT4 | `0x03E0` (no blend) |
| X 72–75 | 8bpp CLUT, STP=1, semi FT4, ABR1 additive | `0xFC1F` |
| X 88–91 | 8bpp index 0 over opaque blue | `0x7C00` (no overwrite) |
| X 104–107 | 4bpp texture window remaps V0..3 to V8..11 | `0x03FF` |

For the fifth patch, **GP0(E2) `0xE2008020`** sets a vertical
texture window mask of one 8-texel unit and vertical offset of one.
PS1 texture-window mapping is
`V'=(V & ~(maskY*8)) | ((offsetY & maskY)*8)`: Y0..3 samples V8..11,
switching CLUT index 1 to 3. Source UV U and texture page remain the
same. The program restores `GP0(E2) = 0` afterward.

The expected colors come from separately written BGR555 expectations.
With blue = `0x7C00` and STP red = `0x801F`, ABR0 averaged red/blue
should be `0xBC0F`, ABR1 additive red/blue `0xFC1F`.

## Pixel-level acceptance

The opt-in pinned-emulator flag `--vh75-stp-e2v-smoke` runs only
a marker-matched, fully synthetic PS-X EXE. It executes the MIPS
interpreter, verifies the RAM marker and exact PC, then flushes the
real PCSX GPU plugin with `GPU_freeze(SAVE=1)` and reads its original
1024×512 native 16-bit VRAM.

**Every pixel** in X39..111, Y103..109 is compared against an
independently fixed BGR555 oracle: 73×7 = **511 pixels**, of which
80 are foreground and **431 must remain zero**. The case refuses even
one mismatch and reports only aggregate counts; no original game data
or pixels are exported. GPU input MMIO and GPU plugin callback records
are separately cross-checked against the exact synthetic stream.

The GCC and Clang CI also runs five **valid-tag, deliberately altered
synthetic MIPS executables**, all of which must reach CPU execution
and be refused at the actual VRAM comparison:

1. Clear CLUT4 palette index1's STP bit.
2. Clear CLUT8 palette index17's STP bit.
3. Change the 8bpp ABR1 tpage to ABR0.
4. Disable the vertical GP0(E2) window.
5. Replace four rows of 8bpp index0 transparent source texels with
   opaque index17 texels.

An invalid-tag EXE is separately rejected before MIPS execution.
The 48 new v75 unit tests and inherited v45–v74 original
GPU/GTE/PRS/OT/VHT1/PS1 DMA/MIPS/private-capture suites are required
on **both** native compiler configurations.

## What v75 cannot establish

The independent oracle measures one **synthetic scene in a pinned
PCSX software renderer**. It is not a verified capture of MAP02
from an authentic retail PlayStation, and is not a source of original
art assets. Complex game polygon ordering, original CLUT coordinates,
texture windows, sprites and Nintendo Switch GPU pixels remain to be
checked separately.

The following remain **false regardless of CI outcome**:

- `retail_ps1_pixel_parity_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

Private original retail GPU captures, raw VRAM, textures and game
media must never enter public GitHub Actions. Keep this work in a
stacked **DRAFT PR** on v74, without merging into `main`.
