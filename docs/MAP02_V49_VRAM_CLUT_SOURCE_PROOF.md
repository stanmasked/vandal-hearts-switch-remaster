# MAP02 v49 — independently verified texture-source VRAM and CLUT addressing

**CI verification:** [GCC + Clang successful run 38924649431](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38924649431).

## Engineering milestone

Previous stages proved:
- v45 safe bounded PRS decomposition and texture GFX accounting;
- v46/v47 the original face's exact OT token, even if GFX/UV/CLUT match;
- v48 the original 15-bit front color and framebuffer before/after **PutPixel**.

**v49 now inspects the texture source before any framebuffer write.**
The read-only patch `tools/instrument_map02_v49.py` is applied in CI only,
after v39 through v48, to the pinned public PC-port revision
`14552fffa0e0b47e02b57592e274fc6e7a649923`.

The instrumented code remains the actual `pc_raster.c::dda_span`.
It does not rewrite `SampleTexture`, `PutPixel`, blending, original
transparency decisions, GTE geometry, sprite classification or OT order.

For each sparsely observed tagged terrain texel, it logs **before PutPixel**:

- `f,token,gfx,route,target,x,y,u,v`: exact frame and face-provenance
  and the individual native or deferred-hires output pixel position;
- `tpage,clut`: actual primitive texture page and palette pointer;
- `maskx,masky,offx,offy`: original GP0 texture-window state;
- `tx,ty,word`: actual packed source texture VRAM halfword address
  and the word obtained by an independent read of live C VRAM;
- `index,palx,paly,palette`: decoded palette index and actual
  CLUT word address/value, or -1 index/address for direct 15bpp;
- `raw`: actual sampled texel (including high STP bit) returned by
  the original `SampleTexture`.

The C source probe derives a second address without calling
`SampleTexture` again; the pre-write snapshot avoids checking a
source word after a potentially overlapping destination write.
It bounds-checks its own VRAM/CLUT accesses, skipping unaddressable
observations. The original (trusted-game) sampler has its original
bounds assumptions, which this diagnostic patch does not change.

Enable this observer only with **both**
`VH_MAP02_V48_TRACE=1` and `VH_MAP02_V49_TRACE=1`, along with the
existing v39 tagging observer. Unset both variables otherwise.
HD-pack replacement pixels are intentionally outside this test.

## Independent reference

`tools/verify_map02_vram_v49.py` checks every v49 source sample
against the matching v48 raw texel and original v47 face/OT metadata,
then computes the lookup independently in Python:

1. GP0 texture-window: `u' = (u & ~(maskX*8)) | ((offX & maskX)*8)`,
   likewise `v'`.
2. Texture page: `pageX = (tpage & 15)*64`,
   `pageY = ((tpage>>4)&1)*256`,
   `depth = (tpage>>7)&3`.
3. 4bpp: read the appropriate nibble of a 16-bit word at
   `(pageX + u'//4, pageY + v')`.
4. 8bpp: read the appropriate byte of the word at
   `(pageX + u'//2, pageY + v')`.
5. 15bpp: read the direct word at
   `(pageX + u', pageY + v')`, without CLUT.
6. Indexed entries: read CLUT at
   `((clut&63)*16 + index, (clut>>6)&511)`.
7. Verify observed texture address, palette address, index, sampled
   BGR555 texel, plus exact v48 original before/after pixel output
   decision. No cross-pixel native-vs-hires color equivalence is
   inferred from different output coordinates.

Malformed, missing or duplicate source observations, out-of-range
addresses, wrong word/index/CLUT, and foreign token/GFX provenance
all fail closed. JSON reports deliberately fix
`original_texture_bytes_authenticated: false`,
`retail_map_authenticity_proven: false`,
`genuine_gameplay_proven: false` and
`HD_replacement_approved: false`.

## Reproduction

With a **single instrumented process's** GPU stderr and the matching
locally owned PRS file:

```bash
python3 -m tools.verify_map02_vram_v49 \
  /private/M_MAP02.PRS \
  /private/same-run-gpu-stderr.log \
  --output /private/map02-v49-vram-report.json
```

Only for synthetic tests, add `--synthetic-fixture`.

This tool emits JSON summary counts and error reasons, **not** user game
asset files, original texture image bytes or vertex arrays.

## Verified automated evidence

Workflow: `.github/workflows/map02-v49-vram-clut.yml`.

| Component or regression | GCC | Clang |
|---|---|---|
| v45 bounded PRS tests | 34 PASS | 34 PASS |
| v46 face identity tests | 21 PASS | 21 PASS |
| v47 all-face exact OT tests | 21 PASS | 21 PASS |
| v48 BGR555/STP/ABR arithmetic tests | 25 PASS | 25 PASS |
| v49 VRAM/CLUT/window tests | 28 PASS | 28 PASS |
| **Python tests per compiler** | **129 PASS** | **129 PASS** |
| Original PC PRS decoder + RenderMapTile + real GTE/GPU | PASS | PASS |
| Independent VRAM source/CLUT check of *actual* C trace | PASS | PASS |
| Negative mutations of actual indexed word/palette/CLUT address | REFUSED | REFUSED |
| Original GPU native/hires one-vs-two-thread frame equality | PASS | PASS |

The original map samples are **SYNTHETIC**:
a 28x12 MapTileModel grid with 3 observed terrain primitives, including
two same-GFX faces in one frame, and a deliberately synthetic 4bpp
palette/VRAM texture. Their original texture page and CLUT metadata
come from the user's established v24 120-entry lookup.
Actual `indexed4` source-word / CLUT observations are made by the
executed real GPU. The 8bpp, 15bpp, texture-window offset/mask variants,
transparent texel, STP and invalid address scenarios have **independent
unit-test vectors**, NOT matching full-game runtime samples.

The CI artifacts `map02-v49-gcc-real-gpu-synthetic` and
`map02-v49-clang-real-gpu-synthetic` contain binaries, build proof,
synthetic PRS, original source logs and v49 JSON. Artifacts may expire.

## Limits and next engineering gate

This is an **internal two-path consistency check on the same live PC-port
VRAM** (original `SampleTexture` versus independent source-word read
and Python address/CLUT calculation); it is not an independently acquired
snapshot of the original retail game's VRAM. It cannot prove original
asset authenticity or full-map source-texture pixel fidelity.

The retail `M_MAP02.PRS`, original CD/TIM texture data and actual
full-game play session have NOT been processed by v49. No Switch
remake binary, HD artwork substitution, original-game screenshot match
or production-asset authorization is claimed.

The next strong proof should exercise actual 8bpp/direct15 reads,
nontrivial GP0 texture-window state, zero texels and STP/ABR blend
decisions **inside the true native raster**, with separate
non-commercial fixtures, before enabling opt-in HD replacement.

This is a stacked draft PR based on v48, without merging to main.
