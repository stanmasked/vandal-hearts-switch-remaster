# MAP02 v167 — guest-MIPS GP0(A0) textured FT4 → real Unai VRAM

This stage combines the established *independently authored* synthetic v72
FT4 pixel oracle with the strict native MIPS-origin checks developed in v166.
It uses a standalone synthetic PS-X EXE (4 KiB), **not** original retail
Vandal Hearts MAP02 game code, media, or textures.

The signed, self-authored `VH72SYN!` program performs an interpreted CPU
GPU FIFO reset (one GP1 word), then 72 MIPS-authored GPU GP0 writes:
draw area/mask/texture-page setup, an A0 upload of 8×4 15bpp texture pixels
with selective STP bit, four blue 4×4 backdrops and four textured FT4 quads
(9 words per polygon).

The v167 read-only observer is installed at the genuine pinned
`psxMemWrite32` entry **before** the old optional v138 observer. The
expected source PCs, full 32-bit command values and exact `SW t1,0(t0)`
opcodes are generated exclusively from the existing synthetic program's
MIPS instruction tuples. All 72 GP0 writes must match; the single GP1
reset must precede them. Normal guest RAM stage-marker stores are ignored.

After the native interpreter finishes, the existing v72 FT4 **Unai VRAM**
oracle must independently pass all 378 pixels in the 54×7 readback region:
16 opaque red pixels, 16 STP ABR0 average-blended pixels, 16 pixels
without STP under ABE, 16 additive ABR1 pixels, and 314 unchanged
background guard pixels.

Native success (both GCC and Clang required):

`VH167_GUEST_MIPS_FT4_VRAM_PASS gp0_words=72 gp1_words=1 ft4=4 texture_upload=1 pixels_checked=378 opaque=16 abr0=16 no_stp=16 abr1=16 guard=314 original_retail=0`

A native rejection mutates one MIPS LUI instruction in the independently
authored program, turning the first FT4 polygon opcode from 0x2D to 0x2F,
while keeping the synthetic executable tag intact. It must be rejected
with exit 72 and `VH167_FT4_MIPS_GP0_REFUSED` **before** the texture
image can be credited. Compiled GCC/Clang tests separately reject wrong
MIPS PCs, opcodes, absent reset, mismatched/extra/unfinished GP0 commands.

**Limitations:** These four polygons are test graphics from synthetic
MIPS code. They are not the actual Vandal Hearts MAP02 map, game camera,
battles, retail FT4 packets or Nintendo Switch HD rendering. No original
private game data or source textures are published.
