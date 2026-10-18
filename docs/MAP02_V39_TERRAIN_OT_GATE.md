# Map 02 v39 — terrain provenance through the real OT and DDA

**Status:** native *object-compilation* and partial-link proof complete. The original
game has **not** been linked or run with this instrumentation. This is not an HD
texture replacement, and does not establish visual correctness.

- Source: `HalmyLyseas/VandalHearts-PcPort`, pinned at
  `14552fffa0e0b47e02b57592e274fc6e7a649923`.
- CI: [Map02 v39 successful run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38829952101).
- Evidence: `map02-v39-gcc-native-proof` and
  `map02-v39-clang-native-proof` in that run (compiler object files, symbol
  tables, SHA-256 manifests). Those GitHub artifacts may expire.
- This work lives in a *draft PR*, not in the default branch.

## Mechanism

1. The three actual terrain-producer functions in `src/core/graphics.c`
   (`RenderMapTile`, `RenderEdgeMapTile`, `RenderOverheadMapTile`)
   call `AddPrim` unchanged.
2. Immediately after `AddPrim`, and only when `gState.mapNum == 11`,
   `PC_Map02V39MarkSubmitted` attempts to annotate the newly minted OT token.
3. The sidecar tag records GFX and the renderer path. The token is marked only
   when the latest minted primitive pointer matches, the bucket contains the
   expected token, and the token is not itself an OT bucket. Tags are cleared
   whenever the corresponding token is minted or recycled.
4. `DrawOTag` walks the actual OT token chain. On a tagged `POLY_FT4`,
   it emits `[v39-terrain-ot]` and makes the tag available **only during**
   its synchronous native `FillQuad` call.
5. The real fixed-point DDA can emit `[v39-terrain-dda]` with matching token,
   GFX, path, sampled native UV, BGR555 texel, transparency and ABR metadata.
   Sampling is sparse (both screen x and y divisible by 32); absence of DDA
   events for a small/occluded face does **not** mean it was not rendered.

Run-time tracing is opt-in via the *presence* of `VH_MAP02_V39_TRACE` in the
process environment. Setting its value to `0` **still enables it**: remove the
environment variable to disable tracing. The instrumented checkout and runtime
must be built explicitly; creating the CI artifacts does not run gameplay.

## Important boundaries

- The graphics compositor's original `FillQuad`, `HiresAppendQuad`, native
  VRAM sample and pixel-write calls remain unchanged.
- The v39 sidecar does not identify sprites solely by UV or CLUT. They have
  no terrain-origin tagging call; accidental UV overlap cannot mark a sprite.
- Only synchronous **native** DDA pixels are covered. Deferred multithreaded
  supersampled passes require a distinct per-primitive tag field in the hires
  display list before HD replacement can be safely enabled.
- No v24 texture lookup, HD asset loading, GPU blending change, STP rewriting
  or Switch executable is part of this gate.
- The existing M_MAP02.PRS / M_MAP02.DAT ambiguity for selected faces must
  be verified from real game observations, not inferred from compile success.

## CI reproduction

The workflow `.github/workflows/map02-v39-terrain-provenance.yml` checks out
the pinned PC-port source, applies the existing read-only map trace patch,
generates v39 diagnostics only in that checkout, and compiles four actual
upstream objects with GCC and Clang. Both builds also run the portable
OT-tag regression, partially link those objects, and reject unresolved v39
symbols. Source anchors, upstream blob identities and modified-path scope are
checked. No proprietary disc image, extracted map, executable or PNG is needed.

## Next validation gate

Build a private local copy of the full PC-port using the user's legitimately
obtained game data; capture a native-frame trace on runtime map 11. Check that
each DDA sample's token matches a terrain-tagged FT4 event in that frame and
compare the BGR555/STP results to the original rasterizer. Only after this can
one design a per-primitive, native-and-hires HD sampler without interfering
with sprites, blend modes or draw ordering.
