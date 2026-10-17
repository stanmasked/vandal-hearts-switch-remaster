# MAP02 — runtime smoke of the real original-PC rasterizer

The original GPU **object compilation and relocatable linking** gate is
described in [map02-real-gpu-compile.md](map02-real-gpu-compile.md).
This second gate **executes** the original upstream rasterizer's native
Draw/Blend path using synthetic, asset-free geometry and VRAM.

## Command

On Linux with a C99 compiler, from this remaster repository:

```sh
python3 -m tools.check_map02_original_raster_runtime /private/VandalHearts-PcPort
```

The upstream copy must contain pristine
`platform/pc/src/pc_raster.c` from pinned commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`.

The command instruments a temporary copy, then compiles and runs it
in two configurations: `ordinary` and
`VH_MAP02_SCOPED_BLEND_PROBE`. Its real execution path is:

```text
original FillQuad
  → FillTriangleDDA
  → PutPixel
  → original BlendG1 (ABR 0 / 1 / 2 / 3)
  → native s_vram result
```

The synthetic fixture sets up a known 5×5 screen quad, a native
`RenderCtx` with scale 1, a low-red BGR555 background word,
and a single selected pixel. For each ABR mode, the test checks that
actual VRAM changes. With the probe enabled, it checks the real
BlendG1 entry arguments (`fg` with bit 15 set, `bg` from VRAM),
the returned word, the completed pixel write, contiguous event
ordering, and the original primitive type. It fails if any ABR mode
has no directly witnessed BlendG1 operation.

A small **headless stub** disables external HD-pack/language
dependencies. This is safe specifically because the fixture only
renders an untextured quad to native VRAM; the full game build must
never replace these dependencies with stubs. No PS-X executable,
disc assets, VRAM dump, or private screenshot is used. The test
does not invoke the real `libgpu.c DrawOTag` walker,
load original game data, or prove PS1 hardware blend equivalence.

## CI history

The earlier successful
[MAP02 object-link run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38986150920)
established 43 passing synthetic regressions and all three original
PC GPU object-link configurations.

The first new runtime job detected a **fixture mistake**: an all-red
saturated BGR555 background (`0x001F`) was unchanged by ABR=1
addition because of 5-bit saturation, even though original BlendG1
was working. Switching the synthetic initial word to `0x0001`
made the observed additive blend measurable. The
[corrected ABR=1 runtime run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38986538352)
completed successfully.

The [four-ABR runtime run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38986618911)
at commit `99253bbf` **completed successfully**. In addition to the
ordinary native raster pass, the scoped mode requires at least one
observed original BlendG1 call for each ABR mode 0, 1, 2 and 3, and
checks native VRAM before/after continuity, argument bit 15 and the
source primitive ordinal for those synthetic draws.

**Limits:** these runtime tests establish a meaningful native raster
execution proof, not a playable port, authenticated MAP02 footage,
complete pixel coverage, or correctness relative to physical PS1.
