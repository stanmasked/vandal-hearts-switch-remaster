# Map 02 v42 — executable REAL PC GPU, synthetic scene

## Confirmed technical milestone

**[Successful final v42 CI — GCC and Clang](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38865415285)**

Unlike the object-only gates v38–v41, this stage **links and runs** the
actual pinned PC-port GPU sources:

- `platform/pc/src/libgpu.c`: genuine OT token minting, `AddPrim`, `DrawOTag`.
- `platform/pc/src/pc_raster.c`: genuine native and multithreaded hi-res
  rasterization, texture decoding, BGR555 modulation and pixel writes.
- Existing v39/v40/v41 read-only instrumentation added to a temporary
  checkout of public upstream commit
  `14552fffa0e0b47e02b57592e274fc6e7a649923`.

Tests use a **synthetic** 15bpp texture, manually constructed FT4 polygons
and test-only shims for window presentation, background packs, language packs
and trace recording. The real game model/terrain creation and loading,
original PS1 executable, disc, map assets, game state and user art are
**not executed or bundled**. No HD texture substitution is enabled.

## Scenario

- Two frames submit one explicitly marked map-11 FT4 each (GFX 641 and
  643), and another unmarked FT4 sprite with identical UV/tpage/CLUT.
- A third frame sends a GFX-644 FT4 but supplies the wrong map number, so
  it must rasterize without acquiring a terrain provenance marker.
- 64 filler TILE primitives force the actual hi-res display list over its
  `s_hprimCount >= 64` threshold and activate the two-band worker path.
- Native and hi-res pixels are checked with `StoreImage` and
  `PC_GpuHiresBytes`, not with a simulated renderer.
- Captured stderr from the **executable itself** goes through
  `tools/verify_map02_v41.py`, yielding exactly two matching
  (frame,OT token,GFX,route) pairs and no orphan or mismatched events.
- The same scene is executed twice using `VH_RASTER_THREADS=2` and
  `VH_RASTER_THREADS=1`. FNV64 of both complete native and hi-res
  framebuffer byte arrays must match exactly.

## CI evidence

| Check | GCC | Clang |
|---|---|---|
| Compile original libgpu.c + pc_raster.c | PASS | PASS |
| Link and execute headless GPU test | PASS | PASS |
| Correct native pixels and hi-res pixels | PASS | PASS |
| Correlated OT/native/hi-res events | PASS | PASS |
| Same-texture, untagged sprite remains untagged | PASS | PASS |
| Wrong-map polygon remains untagged | PASS | PASS |
| Native/hi-res framebuffer equality (1 vs 2 threads) | PASS | PASS |

The observed test-framebuffer FNV64 hashes are the same for both
compilers and both threading modes:

- Native framebuffer: `00ce21774d30c383`
- Hi-res framebuffer: `533ded302eec0383`

The native and hi-res hashes are **not expected to equal one another**
because the buffers have different dimensions and sample positions.
Equality is asserted for the *same buffer* rendered with one or two threads.

The run attaches two GitHub Actions artifacts:

- `map02-v42-gcc-real-gpu-synthetic`
- `map02-v42-clang-real-gpu-synthetic`

Each includes the executable, compiled objects, source hashes, full
synthetic runtime stderr and frame-aware JSON correlation results.
GitHub may expire historical artifacts; the workflow regenerates them.

## Reproducing

1. Run `.github/workflows/map02-v42-gpu-runtime.yml` on the branch, or
   checkout the public upstream source at the pinned commit.
2. Apply `make_map02_trace_patch.py`, then
   `instrument_map02_v39.py`, `instrument_map02_v40.py`, and
   `instrument_map02_v41.py` in that order on a disposable source tree.
3. Compile **the actual** GPU C source units with
   `tests/map02_v42_gpu_runtime.c` and
   `tests/map02_v42_test_shims.c` and link with pthread and libm.
4. Run the program with one and two render worker threads; feed stderr to
   the v41 analyzer; check framebuffer hashes and token/GFX consistency.

The smoke test intentionally calls `PC_Map02V39MarkSubmitted` directly
after `AddPrim` to simulate the verified call made by the terrain
producer in `graphics.c`. The executable therefore **does not prove**
that the entire real game loader and GTE-produced polygons work.

## Remaining work

The next gate is the full PC-port executable, which needs user-owned
original game assets and the required font/binary inputs. Once an actual
map-11 session is available, replay these origin and framebuffer checks
on true terrain, including texture window, CLUT, transparency and
render-order coverage. After that, enable an opt-in HD-texture sampler
only for safely proven terrain primitives. This document is not evidence
of a playable remake.
