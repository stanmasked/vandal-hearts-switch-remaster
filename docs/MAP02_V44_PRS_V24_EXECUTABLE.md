# MAP02 v44 — original PRS decompressor + real v24 texture table + game renderer

**Milestone:** the original public PC-port map decompressor has now been **executed** in the same process as the original game terrain renderer, GTE and GPU. The original retail map data was **not** available; all model geometry and VRAM color entries in this test are synthetic.

## Verified results

**[Successful GCC / Clang run № 38867383563](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38867383563)**

Original pinned public upstream:
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.

1. The actual `src/maps/unpack.c` functions `UnpackMapFileData` and `ProcessMapFileData` decode a synthetic compressed PRS-shaped payload into `gMapDataPtr`.
2. The decoded buffer contains **28 columns × 12 rows = 336** unmodified-layout `MapTileModel` objects, a total of **102,144** bytes. The synthetic literal-coded stream is **114,912** compressed bytes, plus the actual 4-byte length prefix required by `ProcessMapFileData`.
3. The smoke checks the real `UnpackMapFileData` reported decompressed byte count against exactly 102,144, compares every output byte with the synthetic source, and verifies output canaries for both direct unpack and the PRS wrapper.
4. Pointers `gMapRowPointers[0..11]` are assigned into this **decompressed** buffer with the original row-major `[12][28]` stride. The test does not render from the undecoded fixture.
5. The *original* `src/core/graphics.c::RenderMapTile` consumes the decompressed face's `SVECTOR` vertices, `gfx`, `faces` and `shades` and uses the original `platform/pc/src/libgte.c` to project and determine OT depth.
6. Original `AddPrim → DrawOTag → FillQuad → DDA` rasterizes both native VRAM and the threaded hi-res target. v39–v41 diagnostic OT/frame correlation validates the identity of exactly two marked terrain-like faces, and refuses to classify same-texture untagged FT4 sprites or a wrong-map FT4.

## The genuine v24 metadata (no artwork included)

The table at `tests/fixtures/vh_map02_hd_lookup_v24.h` was copied **unchanged** from the user's project Library `vh_map02_hd_lookup_v24.h`. It contains 120 texture entries, among them 96 original canonical masters plus 24 rotated variants. No PNGs, textures or proprietary game disc files are bundled.

The test checks `VH_Map02Find`, `VH_Map02ToMaster`, two special entries and the exact `POLY_FT4` UV corners produced by the original game C function:

| Global game GFX | Local v24 slot | tpage | CLUT | Origin (u,v) | Extent |
|---:|---:|---:|---:|---:|---:|
| 641 | 241 | 5 | 31978 | (240,192) | 16×16 |
| 643 | 243 | 5 | 31850 | (240,208) | 16×16 |

These special slots have different CLUTs. The test generates **synthetic 4bpp VRAM cells** and **synthetic BGR555 CLUT entries** at the real coordinates; the produced colors are not restored MAP02 textures. There is no entry for local slot 242 in the v24 table, and the test deliberately skips it rather than fabricating a GFX mapping.

## Cross-compiler and multi-worker verification

| Evidence | GCC | Clang |
|---|---|---|
| Compile original `unpack.c`, `graphics.c`, `libgte.c`, `libgpu.c`, `pc_raster.c` | PASS | PASS |
| Execute original decompression of complete 28×12 grid | PASS | PASS |
| Exact byte comparison and canary preservation | PASS | PASS |
| Original texture/GFX mapping validated against v24 | PASS | PASS |
| Produce rasterized native/hi-res pixels | PASS | PASS |
| Origin/frame/OT-tag correlation and sprite protection | PASS | PASS |
| Same framebuffer when rendering with 1 vs 2 workers | PASS | PASS |

Complete-buffer FNV64 fingerprints, identical on GCC and Clang and between 1 and 2 raster threads:

- Native BGR555 VRAM: `2f82ee4738d5fe61`
- Deferred hi-res buffer: `4a4c04d1e589f743`

The hashes **across different buffers** should not be equal (their sizes differ). The proven equality is **within each buffer** under different worker counts and compilers.

CI uploads `map02-v44-gcc-real-gpu-synthetic` and `map02-v44-clang-real-gpu-synthetic`, preserving objects, executable, synthetic runtime stderr, JSON correlated report and SHA-256 manifests. GitHub artifacts may expire.

## Architectural confirmation from the pinned upstream source

`LoadMap()` in `src/states/game_setup.c` selects `CDF_M_MAP02_PRS` specifically for **`gState.mapNum == 11`**, with `gMapDataSizeX = 28`, `gMapDataSizeZ = 12`, `gMapSizeX = 24`, `gMapSizeZ = 12`. The project v39 terrain tagging gate uses exactly the same runtime map number.

The CI test does **not** call `LoadMap` or `LoadCdFile`: these functions depend on the actual game data and runtime state. Instead, it executes the original two-stage decompressor on a synthetic payload with exactly the map's expected model dimensions, sets row pointers as the original loader does, and invokes the real renderer.

## Remaining limitations and next gate

- **No retail `M_MAP02.PRS` was supplied or processed.** Synthetic compressed bytes establish binary interoperability, not conformity of the retail file.
- The original decoder assumes trusted source data and does not accept explicit output capacity. **Do not** run arbitrary/unvalidated PRS files through it.
- Real map source geometry, battle map placement, texture availability, original CLUT contents, model face distributions, animations, transparency and per-pixel HD restoration are **not yet proven**.
- `main` is untouched; this is a stacked **draft** PR based on v43 / v42 / v41 / v40 integration branches.

**Next:** safely inspect a user-authorized `M_MAP02.PRS` in a bounded preflight, decode its actual faces, check per-GFX slot attribution and v24 coverage, and capture a real mapNum 11 runtime log. Only then should opt-in terrain-only HD texture sampling be attempted in a playable full PC port.
