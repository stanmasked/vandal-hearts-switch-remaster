# Original DrawOTag and Native Rasterizer — Switch Integration Audit

**Source pin:** `HalmyLyseas/VandalHearts-PcPort`, commit `14552fffa0e0b47e02b57592e274fc6e7a649923`.

## Proven path in original PC implementation

In `platform/pc/src/libgpu.c`, `DrawOTag` walks the ordering table and draws primitives through software-rasterizer services in `pc_raster.c`. After the frame is rasterized, it reads the active `DISPENV`, obtains native 1024×512 BGR555 VRAM via `PC_GpuVram()`, and invokes `PC_GpuPresent` with the correct source rectangle. `PutDispEnv` only records display state; presentation occurs after `DrawOTag`, not when that state is set. The supersampled presentation path can instead call `HiresPresent`.

The independent, already-tested integration NRO runs original pinned `PC_GpuInit` and `PC_GpuPresent` through the project SDL2/GLES2 backend on generated VRAM. It does **not** call `DrawOTag`.

## Confirmed object-level progress

- [DrawOTag object CI #38802987267](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38802987267) passed: original `libgpu.c` compiles to an aarch64-none-elf object, defines `DrawOTag`, and still has external references to `PC_GpuPresent` and `PC_GpuVram`.
- [DrawOTag plus raster object CI #38803269505](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38803269505) passed: original `pc_raster.c` also compiles, defines native `PC_GpuVram` and `FillRect`. Its generated object and symbol audit are uploaded with the `DrawOTag` object.
- A narrowly scoped compiler preinclude `tools/switch_psyq_compat.h` defines the `u_char` and `u_short` aliases expected by the clean-room PsyQ headers. No upstream source is modified.

The audit is **compile-only**. Neither object is yet linked into the verified `PC_GpuPresent` test NRO or executed in NeXium.

## Remaining dependency groups and safety gates

`DrawOTag` depends on the software rasterizer's `FillRect`, `FillQuad`, `Hires*` functions and `PC_GpuVram`, plus tracing `Trc*`, resource/HD-pack hooks, and presentation integration. The rasterizer itself depends on `pthread` workers for the optional high-resolution path, `PC_CpuCount`, language-background hooks and HD asset interfaces. Full-object `nm --undefined-only` is a conservative inventory; it includes functions in sections that may not be retained after dead-section elimination.

The next **real engine frame** acceptance test should link these authentic source units with a legitimate ordering-table and native VRAM pipeline, invoke `DrawOTag` in an instrumented Switch NRO, and confirm the downstream `PC_GpuPresent` image in NeXium with controlled primitives. This would be a source-rasterization test, still **not** a playable Vandal Hearts build. Avoid permanent placeholder implementations of actual gameplay or asset systems, and do not ship copyright-protected game resources.

No physical Nintendo Switch execution is confirmed.

## First partial linkage of authentic DrawOTag + software rasterizer

[GitHub Actions #38803479209](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38803479209) **passed** after compiling both original translation units and invoking `aarch64-none-elf-gcc -nostdlib -r` on their object files. The resulting `gpu-raster-combined.o` defines `DrawOTag` and `PC_GpuVram`; `PC_GpuVram`, `FillRect` and `FillQuad` no longer remain unresolved after linking the two source units. The genuine `PC_GpuPresent` remains external, as intended for subsequent linkage with the separately verified Switch observer/GLES2 presentation backend.

This partial link checks symbol compatibility and native-code composition only. It **does not execute DrawOTag**, resolve the full subsystem dependency set, generate a game frame, or produce a playable Switch build. The compiled object and defined/undefined symbol inventories are saved in the CI artifact `original-drawotag-switch-object-audit`.

## Confirmed original ordering-table rasterization running in NeXium

[Original DrawOTag raster to Switch NRO — CI #38805494413](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38805494413) passed **both** target NRO compilation/linking and NeXium runtime screenshot verification. The new asset-free guest probe `probes/pinned_drawotag_switch_smoke.c` calls original `SetDefDrawEnv`, `PutDrawEnv`, `SetDefDispEnv`, `PutDispEnv`, `ClearOTag`, `SetTile`, `AddPrim`, and `DrawOTag`; its native BGR555 framebuffer comes from the unmodified original `pc_raster.c`. The original pinned `PC_GpuPresent` converts the actual rasterized pixels to RGB24 and the project SDL2/GLES2 observer draws the frame under NeXium. This is **not** direct synthetic VRAM filling: the CPU renderer really executes original ordering-table drawing and FillRect for tile primitives.

The independent NeXium job waited for a visible red marker (poll 1), verified the 1280×720 window, matched all four colored corner markers exactly (red, green, blue, yellow), observed center RGB (99,99,140) → (99,99,0), and counted 20,636 changed sampled pixels. Screenshots and the NRO are uploaded as GitHub Actions artifacts.

The test depends on **probe-only inert hooks** for localization, HD replacement and debug tracing (plus previously isolated movie/menu state). These are not substitutes for actual gameplay services; real game bootstrap and assets remain absent. The next step is to exercise additional original GPU primitives (such as F4 polygons and texture-backed paths), then integrate native engine frames with the real region/disc bootstrap. Physical Switch hardware testing remains outstanding.

## Native POLY_F4 quad rasterization confirmed (NeXium)

[CI #38806009204](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38806009204) passed target NRO build/link and NeXium runtime for the expanded `probes/pinned_drawotag_switch_smoke.c`. The probe inserts an original `POLY_F4` quad through `SetPolyF4`, `setXYWH`, `setRGB0`, and `AddPrim`. The pinned upstream `DrawOTag` executes the authentic `FillQuad` path in `pc_raster.c`; the resulting native BGR555 VRAM is passed to the pinned `PC_GpuPresent` and shown by the Switch GLES2 backend.

CI checks the center of that polygon at window pixel (600,200) on both screenshot frames. It measured **exact RGB (255,0,255)** both times. The four original TILE corner markers remained correct, the animated background center changed (99,99,99) → (99,99,206), and 16,684 sampled pixels changed. These assertions establish that **both untextured rectangle and quadrilateral primitives** render correctly end-to-end in the Switch-target emulator.

This test is still asset-free: textured `POLY_FT4`/CLUT sampling, actual gameplay ordering tables, authentic game assets, audio and input are not verified. The only extra service implementations are explicitly test-only placeholders; original libgpu, pc_raster and PC_GpuPresent code is linked, not replaced. Physical Switch validation remains outstanding.

## Indexed POLY_FT4 / CLUT integration candidate (pending CI)

Commits `a78a697e` and `95eeb7cb` extend the **asset-free** NeXium probe with a 4bpp indexed `POLY_FT4`. Two 16-bit packed texture words (indices 1,2,1,2) are uploaded by the **original** `LoadImage` to VRAM at (64,0); a sixteen-entry CLUT at (0,40) maps index 1 to BGR555 red (0x001F) and index 2 to green (0x03E0). `SetPolyFT4`, `setUVWH`, `setTPage`, `setClut` and `AddPrim` feed the original `DrawOTag` which routes to the original 4bpp `SampleTexture` and `FillQuad` implementation. The quad is deliberately separate from the prior F4 test and original corner markers.

The emulator workflow now asserts four alternating red/green sample locations on **both** screenshots, alongside the existing F4, TILE, animation and frame size assertions. **This is only an integration candidate until the new GitHub Actions run has completed and the screenshots have been verified.** Do not count this as a passing 4bpp/CLUT runtime test before CI confirmation. The probe does not use original game texture assets; 8bpp, direct 15bpp texture paths and actual engine frames remain separate gates.

## Independent 8bpp POLY_FT4 / 256-entry CLUT candidate (pending CI)

Commits `d91ad19e` and `40c6198c` add a second indexed-texture quad beside the existing 4bpp candidate. The asset-free probe uploads two 8bpp packed VRAM words (indices 1,2) at (128,0) through the original `LoadImage`, plus a 256-entry CLUT at (0,41): index 1 is BGR555 blue (0x7c00), index 2 is white (0x7fff). `SetPolyFT4`, `setTPage(...,1,...)`, `setClut` and `DrawOTag` exercise the native 8bpp `SampleTexture` path. The NeXium workflow adds two colour probes (blue/white) on both screenshots; existing TILE, F4, 4bpp and dynamic background assertions stay enabled.

**Status: committed, not yet CI-confirmed.** Neither the 4bpp nor the 8bpp additions should be reported as successful NeXium runs until fresh run logs and screenshots establish that result. Separate future gates: direct 15bpp textures, texture window, STP/semi-transparency, real game VRAM uploads and engine frames.

## Direct-colour 15bpp POLY_FT4 candidate (pending CI)

Commits `ea280273` and `3a67680b` extend the same isolated NeXium NRO probe with a 15bpp direct-colour `POLY_FT4`. The original `LoadImage` uploads a 2x2 BGR555 texture at VRAM (192,0), with alternating yellow (0x03ff) and magenta (0x7c1f). The probe supplies `GetTPage(2,0,192,0)`, which selects the native direct-colour `SampleTexture` path, bypassing CLUT. Independent screenshot probes check both texels on both captured frames and retain the prior TILE, F4, 4bpp and 8bpp assertions.

**Acceptance status: committed but unverified on NeXium.** The legacy #38806009204 run predates all indexed/direct-colour additions and proves only TILE/F4. Current workflow runs after these commits must be checked before promoting the three FT4 modes to passing. No copyrighted game assets are introduced.

## Zero-texel transparency regression (pending CI)

Commits `03aa0a7d` and `f59881ec` add a new 15bpp direct-colour texture at VRAM (256,0), uploaded by original `LoadImage` with the first texel 0x0000 and the adjacent texel opaque cyan 0x7fe0. The independent `POLY_FT4` is inserted through `AddPrim` and rendered by pinned `DrawOTag`/native `FillQuad`. A NeXium screenshot probe asserts that the transparent texel leaves the animated background visible (RGB red/green near 99 and blue changing between frames), while the adjacent opaque texel stays cyan.

This only checks fully transparent (zero-valued) direct 15bpp texels and their opaque neighbour. It does **not** establish STP-bit semi-transparency or any indexed CLUT transparency, and neither this test nor the preceding 4/8/15bpp probes is marked passed without a fresh CI runtime run. Previous confirmed #38806009204 is restricted to TILE/POLY_F4.
