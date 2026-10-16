# MAP02 v47 — exact face-level identity for every submitted terrain FT4

**Status:** Verified executable original PC-port GPU path using **synthetic**
map geometry, compressed PRS and VRAM pixels. No original game assets or
retail PRS were consumed. No HD-texture replacement is enabled.

**Validated GitHub Actions:** [GCC and Clang run № 38919964120](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38919964120)

## Why v46 could not handle the full map

The v46 verifier joined the observed first face of two watched tiles to
GPU OT events using `(frame,GFX,route)`. This approach must refuse two
faces with the same GFX in one frame because texture metadata cannot
establish which original tile produced which OT polygon.

v47 introduces a **second, per-OT-token sidecar** carrying the exact
`(z,x,face)` identity of each source tile.

## Implementation

- `tools/instrument_map02_v47.py` patches the pinned public PC-port
  source **only in a disposable CI checkout** after v39/v40/v41.
- All three original producers — `RenderMapTile`,
  `RenderEdgeMapTile` and `RenderOverheadMapTile` — continue to call
  the game's original `AddPrim`.
- Immediately afterward, a read-only helper locates the decoded
  `MapTileModel*` by exact pointer equality against the 12×28
  `gMapRowPointers[z][x]` grid and binds its `faceIdx` to the
  **just-minted OT token**. The helper refuses pointers outside the grid,
  map numbers other than 11 and invalid face indices.
- `libgpu.c` accepts the face tag only if the token still denotes
  precisely that original primitive pointer, is a non-bucket token,
  and already holds a valid v39 terrain marker. This prevents identical
  UV/CLUT sprite polygons from inheriting a terrain identity.
- When an OT token is minted or reused, its v47 face marker is cleared.
  `DrawOTag` reads the matching immutable attribution and emits
  `[v47-terrain-face-ot]` with `f,token,z,x,face,gfx,route,tpage,clut,u,v`.
  The existing v39 native and v40 deferred-hires DDA events remain in
  their original form.

**No graphics algorithm, polygon geometry, STP transparency, CLUT
sampling, blend mode, VRAM writes, hi-res worker scheduling or sprite
behavior was changed.** This is an opt-in diagnostic build only.

## Runtime verification

`tools/verify_map02_faces_v47.py` reads an authorized PRS using the
bounded v45 decoder and the combined GPU stderr of **one session**.
It checks every submitted v39 tagged OT event has exactly one
matching v47 face marker with the **same frame and token**.

For each token, it verifies:

1. Decoded `MapTileModel[z][x]` actually contains `faceIdx` and its
   signed source GFX matches the v47 tag.
2. The actual GPU FT4 and the user's 120-entry v24 table agree on
   tpage, CLUT and the first UV coordinate.
3. The v39 tagged OT's `gfx,route,tpage,clut` match the v47 face
   marker, and its token has corresponding original native and
   deferred hi-res DDA observations.
4. Missing/extra/duplicate tags and malformed DDA logs fail closed;
   sparsely unsampled polygons never count as visually confirmed.

**This test does not prove that every original map face was visited**,
only the source identities of submitted and logged terrain FT4s.
The tool reports total tagged/paired and distinct source face counts,
and keeps `retail_map_authenticity_proven`,
`genuine_gameplay_proven`, `full_map_coverage_proven` and
`HD_replacement_approved` set to `false`.

Usage:

```bash
python3 -m tools.verify_map02_faces_v47 \
  /private/M_MAP02.PRS \
  /private/same-session-gpu-stderr.log \
  --output /private/map02-faces-v47.json
```

For explicitly synthetic test input add `--synthetic-fixture`.
Never combine logs from unrelated processes or frames.

## Verified executable synthetic scenario

The native C harness `tests/map02_v47_same_gfx_runtime.c` starts from
the same fully decoded 336-model synthetic PRS and submits:

| GPU frame | Decoded tile (z,x) | face | Global GFX | v24 slot |
|---:|---|---:|---:|---:|
| 1 | (8,19) | 0 | 641 | 241 |
| 1 | (8,20) | 0 | 641 | 241 |
| 2 | (11,11) | 0 | 643 | 243 |

**The two first-frame faces have identical GFX 641, original tpage 5,
CLUT 31978 and UV (240,192).** Their provenance is distinguishable
only because each submitted face has its own OT token bound at the
point of `AddPrim`.

The original PRS decompressor, `RenderMapTile`, software GTE,
`libgpu.c` and actual native/multithreaded-hi-res `pc_raster.c`
are all compiled and executed with GCC and Clang. Native/hi-res
sampling events are joined for all three source faces. The wrong-map
third runtime frame is still drawn but correctly does not acquire
map-11 terrain provenance. Identical-texture unrelated sprites remain
untagged.

### Tests

The v47 CI verifies the preceding **34 v45 + 21 v46** Python tests,
plus new v47 regressions, real C decompressor six-token differential,
102,144-byte bounded PRS cross-check, and single-versus-two-thread
framebuffer determinism. It also rejects deliberately corrupted
real execution logs (wrong UV, wrong source tile and wrong frame).

An additional v47 unit regression covers `faceIdx=1` in the
**same** model as face 0 with the same GFX; the full native executable
scenario currently covers the two adjacent face-0 polygons described
in the table.

## Remaining limitations

- Retail `M_MAP02.PRS` and original VRAM texels were **not provided**.
- No original PlayStation gameplay, no full PC-port game link and
  no native Switch HD-remake executable are claimed in v47.
- Observed first UV/tpage/CLUT values do not establish full
  color/texture-window or STP/blend equivalence for every pixel.
- Raster DDA sampling is sparse; a small polygon may be submitted but
  have no sampled event, so this tool reports insufficient evidence
  rather than asserting that the polygon was never rendered.
- A direct retail map run and a separate verified HD-texture sampler
  remain required before enabling real asset substitution.

Changes live in draft stacked PR № 16, based on v46; `main` is
untouched.
