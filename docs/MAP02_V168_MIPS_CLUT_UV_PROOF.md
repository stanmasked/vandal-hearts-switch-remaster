# MAP02 v168 — genuine MIPS-indexed CLUT/UV/texture window → Unai VRAM

The prior v167 independently verified four source-authored 15bpp textured FT4
quads with exact MIPS source PCs, GP0 words and 378 Unai VRAM pixels.
The new v168 scenario tests **indexed 4-bit and 8-bit textures**, palette
location (CLUT), FT4 UV and texture pages, and E2 horizontal texture window
remapping. All data originate in the *self-authored* v74 MIPS fixture,
not in Vandal Hearts retail media.

## Source-provenance and GPU chain

A deterministic synthetic PS-X EXE with the unique `VH74SYN!` tag
executes an MIPS GP1 FIFO reset, then **211 GP0 words** using interpreted
`SW t1,0(t0)` instructions. Every word has a unique source-derived
MIPS PC. The v168 read-only native `psxMemWrite32` observer rejects
wrong PC, opcode, GP0 value, order, extra or missing GPU writes.

The GP0 stream includes four A0 VRAM uploads: packed 4bpp texture,
packed 8bpp texture, a 16-entry CLUT and a 256-entry CLUT. FT4 has
four distinct textured quads, including 4bpp palette at CLUT X=512,
8bpp palette at CLUT X=528 with texture page `0x081`, E2 window
`0xe2000401` mapping U0..3 to U8..11, and E2 reset followed by a
transparent palette-index-0 FT4 over a blue background.

The original separate v74 true-Unai VRAM oracle is preserved and must
verify exactly **399 pixels**: 16 from each of 4 textured regions plus
335 unchanged background pixels. It does not rely on v168's expected
GPU packet arrays for its expected pixel colors.

Expected native evidence:

`VH168_GUEST_MIPS_CLUT_UV_VRAM_PASS gp0_words=211 gp1_words=1 a0_uploads=4 ft4=4 pixels_checked=399 clut4=16 clut8=16 e2_window=16 transparent=16 guard=335 original_retail=0`

A negative run mutates a single MIPS LUI in the signed *synthetic*
program, changing the first opaque FT4 GP0 opcode 0x2D→0x2F.
The MMIO observer must return 74 with
`VH168_CLUT_MIPS_GP0_REFUSED` before VRAM success. Both native
GCC and Clang and separate compiled-C regression suites must pass.

## Explicitly not verified

These CLUTs, indices, textures and polygons are self-authored synthetic
test data. This does **not** establish actual retail Vandal Hearts
MAP02 texture pages, CLUTs, in-game geometry, battle screenshot,
Switch rendering, game completeness or pixel parity with original
gameplay. No privately supplied game files, copyrighted textures
or private GPU captures enter public GitHub.
