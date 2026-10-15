# Scene entry: ordering of map and unit scratch3 users

Reference: `HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.
This is a **source call-site audit**, not a complete runtime call graph.

## Direct call sites inspected

At this pinned revision, textual direct calls to `LoadUnits()` and
`LoadMap()` in the three inspected translation units are:

| Call | File and line | Guard / reason |
|---|---|---|
| `LoadUnits()` | `src/core/main.c:378` | Within `gState.primary == STATE_4` |
| `LoadMap()` | `src/core/main.c:388` | `gState.scene == 39` |
| `LoadMap()` | `src/core/main.c:397` | `gState.scene == 88` |
| `LoadMap()` | `src/core/main.c:414` | `gState.scene == 61` |
| `LoadMap()` | `src/core/main.c:431` | `gState.primary != STATE_16` |

`src/states/game_setup.c:1840` defines `LoadMap()`.
`src/units/load.c:75` defines `LoadUnits()`. Both are called directly
from the scene setup block in `src/core/main.c:368-434` above.

Within a **single pass through this block**, the lexical ordering is:

1. Optional `LoadUnits()` (subject to `STATE_4`)
2. Optional map loads for scenes 39, 88 and 61
3. Optional general `LoadMap()` if the primary state is not `STATE_16`
4. `SetupField()` and `SetupLight()`

If a special-scene condition is true and the general condition is also
true, `LoadMap()` can run twice within the block. A `STATE_16` path can
skip the final general map load. Hence **do not assume every scene setup
ends by reloading a map**: the exact active state matters.

## Scratch3 alias and consequences

`LoadUnits()` reads its per-unit file using `LoadCdFile(..., 1)` into
scratch3 base, while it accumulates decoded sprite-sheet content at
scratch3 + `0x2db80` (or + `0x3a300` for map 39).
`LoadMap()` decompresses from scratch1 into scratch3 base.

This means a previously decoded map view must be invalidated before a
unit file is staged, then revalidated only after an actual successful
map reload. The separate test-only `VhMapUnitPhase` state models this
contract; it does not intercept the real engine's reads and writes.

## Additional work before actual engine port

* Trace each state transition into this block and any indirect / dynamically
  dispatched map or unit loads; the above grep is **not exhaustive**.
* Analyze scene 39/61/88 and `STATE_16` with actual execution traces.
* Check whether `SetupField()` consumes a still-valid map if a general
  reload is skipped.
* Determine the lifetime of pointers and the maximum span written by
  `LoadCdFile` (including unit staging).
* Run real-asset checks locally without committing proprietary game assets.

Synthetic scenario tests model both the ordinary final reload and a path
where the final reload is absent, and must reject stale-map consumption.
