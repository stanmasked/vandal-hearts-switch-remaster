# MAP02 v74 — 4-bit/8-bit CLUT indexed textures and GP0(E2) window

## What this test actually proves

Building on v73 native VRAM verification, v74 exercises PS1 indexed texture
lookups through **two CLUT palettes**, switching from **4bpp to 8bpp**
texture pages, GP0(E2) texture-window remapping, and zero-index transparency.

The fixture is **100% original synthetic input**: a Python-created 6144-byte
PS-X EXE (2048-byte header plus 4096-byte MIPS-I payload). The MIPS
interpreter from pinned PCSX ReARMed actually executes every GPU register
write. Real `GPU_freeze(1)` flushes rendering and exposes native 16-bit
1024×512 VRAM. The diagnostics compare **399 independently specified
pixels** (64 foreground and 335 guards), not just GP0 callback counts.

Source emulator: `notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e`.
Hardware description: [psx-spx rendering attributes](https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/)
and [PS1 VRAM indexed packing](https://psx-spx.consoledev.net/dev/ps1/gpu/video-memory-vram/).

## Test scene

The CPU sends four native GP0(A0) uploads:

- **4bpp texture page 0**, 4 VRAM halfwords × 4 rows, 16 four-bit indexes
  per row: `1,2,3,4,0,0,0,0,5,6,7,8,0,1,2,3`. Index 0 is
  transparent. Four indices are stored in a little-endian 16-bit word.
- **8bpp texture page X=64**, 4 halfwords × 4 rows, eight indices per
  row: `17,34,51,68,0,0,0,0`. Two indices per 16-bit VRAM word.
- **4bpp CLUT at VRAM X=512,Y=0**, 16 BGR555 entries. CLUT field
  is `CLX=512/16=32`.
- **8bpp CLUT at VRAM X=528,Y=0**, all 256 entries, with distinctive
  colors at indexes 17,34,51,68. CLUT field is `CLX=33`.

The loaded palettes and FT4 packets drive these four distinct 4×4
rasterized patches at Y=80..83:

| Destination | GPU effect | Expected BGR555 pixel sequence, each row |
|---|---|---|
| X=40..43 | 4bpp + CLUT 32 | `001F, 03E0, 7C00, 7FFF` |
| X=56..59 | 8bpp + CLUT 33 | `4210, 7C1F, 7FE0, 03FF` |
| X=72..75 | 4bpp + GP0(E2) window | `03FF, 7FE0, 7C1F, 4210` |
| X=88..91 | 4bpp index 0 over blue backdrop | `7C00, 001F, 03E0, 7C00` |

GP0(E2) `E2000401` sets X mask 1 and X offset 1. Under the PS1 GPU
definition, `U'=(U AND NOT(mask*8)) OR ((offset AND mask)*8)`, so UV
values 0..3 read texels 8..11. The texture window is then reset using
`E2000000` before the transparent-index patch.

This is deliberately a separate mechanism from STP/ABR semitransparency:
zero 4-bit palette index returns **VRAM color 0000h**, which leaves the
previous opaque blue backdrop untouched.

## Fail-closed hardware raster regressions

On **both GCC and Clang**, the workflow must execute native PCSX CPU
code for the correct source-authored EXE, then independently verify
the exact actual GP0 input sequence, original GPU plugin callback
counts and all 399 native pixel values. It must also reject four
otherwise valid-tag PS-X EXEs that make a single falsifiable change:

1. Replace first FT4 CLUT 32 with 33.
2. Replace 8bpp texture page mode with 4bpp.
3. Disable the E2 texture-window remapping.
4. Replace the first zero-index 4bpp texel with index 1 (exposing
   failure of index-0 transparency on at least one pixel).

An EXE with an invalid marker is rejected before executing instructions.
Each case runs through **the actual PCSX interpreter and GPU plugin**
and must fail the *pixel comparison*, not merely parser semantics.

Inherited v45–v73 real-public-PC GPU/PRS/GTE/OT/VHT1, MIPS and privacy
regressions run unchanged. CI contains no retail discs, Sony SDK or
original Vandal Hearts textures.

## Limitations and provenance

One four-patch synthetic software GPU scene does not establish full
CLUT behavior, every texture-window mask and coordinate wrap,
PlayStation retail hardware pixel parity or actual MAP02 geometry
and textures. In particular, this test does not authorize HD
texture replacement on Nintendo Switch.

`authentic_retail_gpu_pixel_parity_verified=false`

`original_retail_MAP02_verified=false`

`HD_replacement_approved=false`

PR remains stacked on v73 as a draft; `main` is untouched.
