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
