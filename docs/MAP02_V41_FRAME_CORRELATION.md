# Map 02 v41 — frame-stable terrain provenance validation

## What v41 fixes

The PC-port ordering table mints a new set of integer tokens in each frame.
The original v39 / v40 native and hi-res DDA log lines had token, GFX and
renderer route but **no frame ID**. A token reused in a later frame could
therefore be accidentally correlated to the wrong polygon.

v41 adds `RenderCtx.v41Frame` and snapshots `s_drawFrame` before
`rch = rcn`. Both native rasterization and each immutable, deferred
`HiresPrim.rc` therefore carry the originating frame into DDA processing,
including when workers rasterize separate screen bands concurrently.
It adds `f=...` to:

- `[v39-terrain-dda]` — original-resolution sampling
- `[v40-terrain-hires]` — deferred sampling at the internal render scale

The prior `[v39-terrain-ot]` event already includes `f=...`, so there
is no need to change the ordering-table walk or its log format.

**Safety:** no texture sampling, BGR555 writes, blending, STP behavior, OT
traversal, sprite classification or original game assets are modified.

## Validation tool

`python3 -m tools.verify_map02_v41 /path/to/combined-stderr.log --output v41-report.json`

The input must be a single combined stderr log from **one real runtime
session**, not a concatenation from several runs. Do not mix logs from
different processes: frame/token collisions between separate sessions
cannot be distinguished.

Exit status:

| Code | Meaning |
|---|---|
| `0` | At least one tagged `(frame,token)` has matching native AND hi-res samples, with no detected contradictions |
| `1` | Invalid/malformed log, stale token, mismatched GFX/route, duplicate OT event, orphan sample or inconsistent texel fields |
| `2` | Insufficient evidence (missing an OT, native or hi-res sample for the same submitted polygon) |

**Status 0 is not visual validation.** Sampling is deliberately sparse:
a polygon with no qualifying pixel might still have rendered correctly.
A match says only that native and hi-res sample events belong to the same
documented polygon identity. It does not compare colors at equivalent
screen coordinates or prove that textures have been artistically restored.

Old v39/v40 DDA log formats *without* `f=` are rejected as malformed
(status 1), not silently correlated with a guessed frame number.

The resulting JSON includes counts of submitted OT polygons, native and
hi-res samples, sampled primitives, paired primitives, unobserved
primitives, frame count, and errors. A negative result can be triaged
without falsely interpreting missing sparse samples as a rendering bug.

## How to generate real runtime evidence

A full PC-port build, compatible user-owned game data and an actual
map-11 gameplay session are still required. Build the instrumented
*temporary* checkout with `VH_TRACE_MAP02` and `VH_MAP02_V39_TRACE`
defined; set `VH_MAP02_V39_TRACE=1` at runtime. Ensure the hi-res
pass is active, for example with `VH_INTERNAL_SCALE=4`, then capture
stderr into one log and run the validator.

In this upstream implementation, the **presence** of the environment
variable `VH_MAP02_V39_TRACE` enables the trace, even if its value is
`0`; unset it to disable tracing.

Sample records currently exclude regions replaced by the existing
HD-pack mechanism. This test validates the original PS1 texture
sampling path only. Do **not** interpret `status=provenance_correlated`
as permission to enable HD texture replacement.

## CI and source isolation

The workflow
`.github/workflows/map02-v41-frame-correlation.yml` compiles real
PC-port C translation units using GCC and Clang at pinned upstream
`14552fffa0e0b47e02b57592e274fc6e7a649923`, performs partial
linking, runs strict Python regression tests and preserves build
evidence in GitHub Actions artifacts.

The changes are in a stacked draft PR targeting the v38-v40 branch,
rather than directly touching `main`. No executable, real frame trace
or external game assets have been produced by this stage.

## Next engineering gate

Once a genuine session log has been obtained, add a *screen-space
coordinate-normalized* comparison of BGR555/STP decisions across the
native and hi-res passes. Maintain separate provenance for every
deferred polygon, rather than relying on global mutable state.
