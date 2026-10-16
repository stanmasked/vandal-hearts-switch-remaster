# MAP02 v72 — textured FT4, GPU texture upload and STP/ABR output oracle

## What was missing after v71

v71 confirmed actual **native VRAM pixels** for a purely synthetic MIPS
program drawing flat rectangles with GPU mask controls. MAP02, however,
relies on **textured polygons**, texture pages, transparency flags
and semi-transparent blending. v72 adds these operations to the
actual emulated PlayStation CPU → PCSX GPU plugin → VRAM readback path.

## Synthetic original test scene

The 4096-byte PS-X EXE is generated exclusively from hand-encoded
MIPS-I opcodes. It contains **no Sony SDK, BIOS, licensed game source,
artwork or audio**. It writes GPU commands to the original
`0x1F801810` register and a GP1 FIFO reset to `0x1F801814`.

The GPU command stream first sets drawing area and offset, then
uses **GP0(A0)** to upload an **8×4 region of 15-bit native VRAM
texels** at texture page origin (0,0), with left four texels per row
being `0x001F` (red with STP=0) and right four being `0x801F`
(red with STP=1). The four scanlines have identical, synthetic texels.

It then paints blue opaque 4×4 backdrops at four separate positions
and draws four FT4 (`GP0(2Dh)` / `GP0(2Fh)`) raw-texture quads:

| Scene | Screen X | Texture U | FT4 mode | Independent VRAM expected |
|---|---:|---:|---|---|
| Opaque raw textured | 64 | 0..4 | 2D, 15bpp | `0x001F` |
| STP enabled, ABR0 | 80 | 4..8 | 2F, average | `0xBC0F` |
| Semi command, no STP | 96 | 0..4 | 2F, texture bit15=0 | `0x001F` |
| STP enabled, ABR1 | 112 | 4..8 | 2F, additive | `0xFC1F` |

The expected BGR555 values come from an **independent color/blend
calculation**, not from the observed emulator framebuffer.
GP0(E1) texture page bits choose 15bpp; FT4's second UV word
supplies tpage with ABR0 or ABR1. Texture samples carry their own
bit15 for selective blending. Test geometry deliberately uses
separate small rectangles to avoid any user/game texture data.

### Real emulator VRAM oracle

The pinned upstream is
[notaz/pcsx_rearmed@8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

The diagnostic `--vh72-ft4-smoke` mode calls the actual emulator's
MIPS interpreter on the source-authored EXE and requires the CPU
completion marker and expected loop PC. Then **GPU_freeze(SAVE=1)**
flushes/synchronizes native gpulib rendering and supplies the actual
1024×512 16-bit VRAM pointer.

The fixed oracle checks x=63..116, y=31..37: **378 pixels**, consisting
of four disjoint 4×4 textured patches (64 pixels total) and **314
unpainted guard pixels**. Any incorrect pixel, even with successful
MMIO logging and GPU callback dispatch, rejects the test.

Actual GPU MMIO and plugin-call journals are also checked separately.
The validation is stronger than observing commands alone, but still
**only concerns this synthetic scene in a PCSX software renderer**.

### Negative tests and provenance

The CI additionally executes deliberately changed **valid-tag
synthetic EXEs** with GPU attributes mutated. Disabling semitransparency
on the first STP-textured quad must produce different native VRAM, and
changing ABR1 to ABR0 must also fail the independent oracle. An
invalid diagnostic marker is rejected before execution. The
39 new unit tests inspect exact FT4 command lengths, texture/UV
word order, 15bpp tpage, expected blending math, CPU instruction
emission, bounds and no-overwrite behavior.

The full inherited v45–v71 original C renderer GPU/OT/VHT1/MIPS
and privacy matrix runs on both GCC and Clang. No real game assets,
original VRAM captures or retail PS1 disc images are uploaded.

Hardware syntax references:
[PSX polygon commands](https://psx-spx.consoledev.net/dev/ps1/gpu/render-polygon-commands/),
[rendering attributes](https://psx-spx.consoledev.net/dev/ps1/gpu/rendering-attributes/),
[GPU VRAM layout](https://psx-spx.consoledev.net/dev/ps1/gpu/video-memory-vram/).

## What is **not** proven

The exact textured FT4 results from PCSX do not establish that every
PlayStation GPU or another PS1 emulator will produce bit-identical
output. The original MAP02 FT4 packets, textures, CLUTs, MAP02
geometry, native Switch rasterization and HD replacements have
**not** been authenticated by this scene.

`authentic_retail_gpu_pixel_parity_verified=false`
`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

The project remains a stacked draft PR on v71; the main branch is
not changed by this milestone.
