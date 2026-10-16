# Map 02 v43 — executable original terrain producer + GTE + GPU

**Verified:** [GCC and Clang GitHub Actions run 38866403395](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38866403395)

## What actually executes

On the pinned public PC-port source
`14552fffa0e0b47e02b57592e274fc6e7a649923`:

1. `src/core/graphics.c::RenderMapTile` reads a test-built `MapTileModel`
   with four original-layout `SVECTOR` vertices and one face.
2. The untouched software `platform/pc/src/libgte.c` performs the
   **actual** `gte_ldv3 → rtpt → nclip → stsxy3 → rtps → avsz4 → stotz` path.
3. The original terrain producer resolves GFX into real PS1 texture-page
   metadata, computes shading, sets `GPU_CODE_POLY_FT4` and calls
   `AddPrim(ot + OT_SIZE - otz, poly)` itself.
4. The v39 metadata sidecar attaches map-11 terrain origin to that exact
   real OT token. `DrawOTag` walks the original link registry.
5. The real production `FillQuad` and DDA rasterize to native VRAM,
   and a deferred immutable `HiresPrim` feeds the native hi-res worker
   code in `pc_raster.c`. v40/v41 diagnostics confirm
   (frame, token, GFX, terrain-route) identities.

The test supplies only the few source globals needed by this function,
test-only window/HD-pack/trace-output shims and synthetic PS1 texture
bytes. No retail executable, disc data, M_MAP02.PRS resource, character
models, original terrain vertices or actual gameplay are involved.

**This is not a full game/HD-remake build.**

## Test cases

- Frame 1: test tile [z=8,x=19], runtime mapNum 11, GFX 641.
- Frame 2: same test tile, mapNum 11, GFX 643; OT tokens reused.
- Frame 3: same tile, mapNum 2, GFX 644. The actual face draws, but
  map-02 provenance is correctly refused.
- For each frame a separate textured FT4 visually mimics the test
  terrain's tpage/CLUT/UV layout. It draws but receives no terrain tag.
- At least 64 TILEs force the actual two-band deferred worker raster.
- A one-worker control run renders the same model. Both complete
  framebuffers are hashed at the end of the three frames.

The actual game-data generator and map loader are not linked. Terrain
GFX assignment and synthetic texture bytes are arranged by the test,
not extracted from Vandal Hearts assets.

## Evidence

| Check | GCC | Clang |
|---|---|---|
| Compile real `graphics.c` | PASS | PASS |
| Compile real `libgte.c` | PASS | PASS |
| Link and execute real `libgpu.c` and `pc_raster.c` | PASS | PASS |
| Game `RenderMapTile` emitted one FT4 on each frame | PASS | PASS |
| Real GTE projected a positive screen area | PASS | PASS |
| Native VRAM / deferred hi-res nonzero pixels | PASS | PASS |
| v41 frame-aware two-polygon OT-DDA correlation | PASS | PASS |
| Lookalike sprite and wrong-map GFX excluded | PASS | PASS |
| Native and hi-res buffers identical with 1 vs 2 workers | PASS | PASS |

Framebuffers (FNV64, matching GCC/Clang and 1/2 render threads):

- Native: `6fe5f83dfe110383`
- Hi-res: `fbb618b2f96d0383`

Different native/hi-res hashes are expected because buffer dimensions
and sampling differ. Identical hashes are required for **the same**
buffer under different worker counts.

The CI artifacts
`map02-v43-gcc-real-gpu-synthetic` and
`map02-v43-clang-real-gpu-synthetic` preserve binary, objects, hashes,
combined stderr and JSON. The direct stderr contains real processed
synthetic frames; the JSON report specifically notes it does **not**
prove original game gameplay or pixel equivalence.

## How to reproduce

The GitHub workflow `.github/workflows/map02-v43-real-producer.yml`
checks out upstream exactly, applies the v39–v41 diagnostic changes
in its disposable checkout, and compiles the original game/GTE/GPU
modules with `tests/map02_v43_real_producer.c` and test-only shims.

The main production paths never link to the shims. The build of the
real graphics source requires the same GNU89 forward-declaration
compatibility wrapper previously verified in v38–v41; no source
commits to the public upstream repository are made.

## Next validation

To inspect **real** map 02:
1. Acquire local, user-authorized original game resources and the
   corresponding PC-port executable/font prerequisites, validated by
   `tools/preflight_map02_pcport.py`.
2. Execute a real mapNum 11 session with the v39–v41 diagnostic
   instrumentation.
3. Run `tools/verify_map02_v41.py` on the **single process** stderr.
4. Compare native/hi-res texture windows, BGR555 STP and blending
   before changing the sampler or enabling any HD replacement.

Provenance tagging, source compilation and synthetic execution do
not establish complete map fidelity or a playable Switch remaster.
