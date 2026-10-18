# Map 02 v40 — deferred hi-res provenance carried per primitive

**Goal:** preserve a confirmed terrain OT token all the way from
`RenderMapTile` / `RenderEdgeMapTile` / `RenderOverheadMapTile` to the
fixed-point DDA in the **deferred hi-res** path, without assigning a global
mutable “current primitive” variable that would race between worker threads.

## Data path

```text
  terrain AddPrim (mapNum==11)
       │ v39 sidecar: token + gfx + route
       ▼
  DrawOTag matches sidecar tag to exact POLY_FT4 token
       ├─ original native FillQuad (v39 observation)
       └─ RenderCtx rch.v40{Token,Gfx,Route}
                  │ immutable context copied into HiresPrim.rc
                  ▼
             HiresRasterizeBand worker (row-partitioned)
                  │ RenderCtx rc = hp->rc (per-band copy)
                  ▼
           FillQuad → FillTriangleDDA → dda_span
                  │ direct per-primitive context read
                  └─ [v40-terrain-hires] token gfx route x y u v
                                       raw draw semi abr scale
```

The three tag fields are initialized to zero for **every native RenderCtx
instance** before the hi-res context is copied. They are populated only
in the tagged terrain `POLY_FT4` branch. Every sprite, rect, untextured quad,
and ordinary texture retains all-zero provenance. Both `HiresAppendQuad`
and `HiresAppendRect` retain their original full `RenderCtx` assignment;
the rest of the renderer's pixel math and blend/write operations are unchanged.

## Important details

- The hi-res draw list stores each `RenderCtx` by value. Raster workers
  take another per-band copy; therefore workers **do not share a writable
  current-token variable**, and tagging cannot bleed into the next FT4.
- The already-established v39 native-path event still uses its own global
  variables during the **synchronous** native draw. v40 never reads those
  variables from the worker threads.
- Logging is sparse at target pixels `x % 64 == 0, y % 64 == 0`. Zero samples
  for a small/cropped polygon do **not** establish absence of rendering.
- An active preexisting HD-pack region (`cx->hdPx`) is excluded from v40
  texel sampling: the observer records the original indexed/15-bit VRAM path.
  Mapping the existing background-replacement path is separate work.
- Multi-threaded messages can appear in non-monotonic order. Correlate events
  using **token, gfx, route, frame context**, not log-line order.
- The presence of the environment variable `VH_MAP02_V39_TRACE` enables
  logging; a value `0` still counts as present. Remove the variable to disable.
- `VH_INTERNAL_SCALE` must make a hi-res target active for deferred events
  to exist (normally 2–4); otherwise there is no deferred hi-res pass.
- Original artwork, STP masks and game disc images are not bundled or
  altered; **no HD texture replacement is enabled**.

## Reproduce native object/partial-link verification

GitHub Actions workflow:
`.github/workflows/map02-v40-hires-provenance.yml`.

The workflow checks out the exact pinned public PC-port revision
`14552fffa0e0b47e02b57592e274fc6e7a649923`, applies the existing
v39 upstream tracing and v40 only in the temporary checkout, validates
source anchors and modified paths, executes nine Python unit tests and
the v39 C89 token test, compiles real upstream objects with GCC and Clang,
and performs a partial link with no missing v39 diagnostic symbols.

**Passing these tests does not prove runtime gameplay or visual correctness.**
The next gate is a genuine full-game link, a runtime trace of mapNum 11, and a
cross-check between [v39-terrain-ot], [v39-terrain-dda] and
[v40-terrain-hires] for identical submitted primitives. An HD sampler must
not be enabled until the original blend/CLUT/STP and draw ordering has
been verified on user-owned game data.
