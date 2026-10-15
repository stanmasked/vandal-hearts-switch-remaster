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
