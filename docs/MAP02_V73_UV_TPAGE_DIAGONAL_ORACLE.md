# MAP02 v73 — FT4 UV scaling, adjacent tpage and STP-textured FT3 diagonal

## New evidence boundary

v72 measured real PCSX ReARMed VRAM output for four synthetic
15bpp FT4 quads, including the texture STP bit and blend modes ABR0/ABR1.
v73 expands to three **different GPU geometry/texture semantics**:
non-identity UV interpolation, an adjacent 64-halfword texture-page
origin, and **a pair of FT3 triangles meeting along one diagonal**.

The pixel source is independently specified; no observed emulator
pixels are copied into the oracle. The original 4 KiB synthetic
PS-X EXE is generated from hand-written MIPS-I CPU opcodes only.
There is no proprietary game data, BIOS or SDK.

### Source VRAM

The MIPS CPU submits **three GP0(A0) native VRAM transfers**.
Each is four scanlines high; all texture bits are 15bpp:

- At VRAM X=0: 8 texels/row with red/green/blue/white repeated twice:
  `001F, 03E0, 7C00, 7FFF, 001F, 03E0, 7C00, 7FFF`.
- At VRAM X=64: four distinct texels/row, yellow/cyan/magenta/grey:
  `03FF, 7FE0, 7C1F, 4210`.
- At VRAM X=128: four texels/row, uniform `801F` (red with
  per-texel STP bit15 set).

These correspond to adjacent PS1 15bpp texture-page bases with
tpage values `0x100`, `0x101`, and `0x102` (X bases
0, 64 and 128 halfwords).

### Destination VRAM

The source-authored GPU operations are:

| Native VRAM destination | Rendering | Exact expected color |
|---|---|---|
| X 40–43, Y 56–59 | FT4 raw texture, U spans 0–8 over four pixels | red, blue, red, blue each row |
| X 72–75, Y 56–59 | FT4 raw, page X=64, U spans 0–4 | yellow, cyan, magenta, grey |
| X 88–91, Y 56–59 | Blue background then **two FT3 semi-textured triangles** sharing a diagonal, from tpage X=128 | 16 pixels `BC0F` (STP ABR0 red/blue average) |

The two triangles should cover the 4×4 destination exactly once.
Any missing pixels along the common edge retain background blue;
any pixels rasterized twice will be blended a second time, giving a
different VRAM color. Hence the STP semitransparency is deliberate:
a single flat opaque color could hide overdraw bugs on the diagonal.

The real instrumented PCSX emulator executes the MIPS code using
the genuine PS1 CPU interpreter, records each GPU input command
word, and synchronizes its **original raster plugin** through
`GPU_freeze(SAVE=1)`. The diagnostic reads the real 1024×512
16-bit VRAM pointer and checks **399 actual pixels** in region
X 39–95 and Y 55–61: 48 colored output pixels and **351 guard
pixels**, against an independent pixel-by-pixel oracle.

### Mandatory negative tests

Three deliberately mutated but otherwise executable **synthetic**
PS-X EXEs must fail on actual GPU pixel readback:

1. Change U span `8` to `4` on the first FT4; the 2:1
   UV stride must be detected as incorrect.
2. Change the second FT4's tpage from X=64 to X=0, retaining
   the rest of its packet.
3. Change one triangle from semitransparent textured FT3
   `0x27` to opaque textured FT3 `0x25`, changing pixels on
   one side of the diagonal.

An altered EXE identity marker is refused before MIPS execution.

The test emits only **synthetic** artifacts to CI.
Never publish user-owned or retail game VRAM, GPU FIFO/GP0 captures,
textures or copyrighted assets. Local private capture outputs and
provenance tracking from stages v60–v72 remain enabled.

### Supported verification / limits

This is a **PS1 GPU software rasterizer experiment in pinned PCSX
ReARMed**, not a claim of pixel-for-pixel parity against original
retail hardware. It exercises one small axis-aligned pair of FT3s,
nontrivial UV interpolation and a 15bpp tpage-X transition; it
does **not** cover all winding orders, texture windows, CLUT modes,
polygon clipping, every STP/ABR combination or actual game MAP02.

The hard gate values remain:

`authentic_ps1_retail_pixel_parity_verified=false`

`original_retail_MAP02_verified=false`

`HD_replacement_approved=false`

The branch is a draft stacked on v72 and has not been merged into
`main`.
