# Map and unit scratch-buffer lifetime audit

Pinned reference: `HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`. Source-based findings only; no original game assets are redistributed.

## Confirmed shared backing

* `src/core/main.c:272`: `gMapDataPtr = gScratch3_80180210`.
* `src/units/load.c:139-145`: `LoadUnits()` places its persistent sprite-sheet/animation output at `gScratch3_80180210 + 0x2db80` normally; map 39 uses `+0x3a300`. It initializes `p = gUnitDataPtr`.
* `src/units/load.c:172-186`: **each requested unit file is read by `LoadCdFile(unitFiles[i], 1)` into the beginning of `gScratch3_80180210`**, and the loader immediately reads that header, sheet size table, sheet pointers, and sprite strips from this same base.
* `src/units/load.c:209-226`: sprite strips are passed to `LoadImage`; sheet words are copied from scratch3's beginning into the separate `gUnitDataPtr` accumulation area.
* `src/states/game_setup.c:2592-2614`: `LoadMap()` calls `ProcessMapFileData(&gScratch1_801317c0[0])`, which decompresses into `gMapDataPtr`, then patches face texture indices from that decoded map, then calls `SetupField()`.
* `src/core/cd.c`'s static file table maps both unit data files and several texture/graphics files to `gScratch3_80180210`, while `M_*.PRS` map files target `gScratch1_801317c0`.

**Implication:** scratch3 base is not permanently reserved exclusively for map tiles. A unit file loaded into scratch3 base can overwrite decoded map bytes at the same addresses. Preserving the source's temporal *load/reuse/restore* behavior matters; distinct host arrays for every symbol would hide these real aliases.

## Confirmed principal scene sequence

In `src/core/main.c:368-434`, during scene setup:

1. When `gState.primary == STATE_4`, `LoadFWD()`, `SetupPartySprites()`, `LoadPortraits()`, **`LoadUnits()`**, and `SetupSprites()` may run (exact conditions in main.c).
2. Sound and special-scene branches may call `LoadMap()` earlier for scenes 39, 88, and 61.
3. If `gState.primary != STATE_16`, the general path calls `LoadFCOM4XX()`, `LoadMapTextures()`, then **`LoadMap()`**.
4. The path then calls `SetupField()` and `SetupLight()`.

This ordering provides a plausible explanation for why temporarily loading unit files into scratch3 base is tolerable on the principal scene path: the map is subsequently reloaded. **It does not prove that every state or special branch follows this order**, nor does it prove how much of scratch3 a unit-file read overwrites.

## Integration requirements

1. Model scratch3 as **one shared allocation**, with time-dependent leases or phase assertions. Never silently replace `gScratch3_80180210` with independent 'map' and 'unit staging' arrays.
2. Before a unit-file read into scratch3 base, mark any decoded map view at base as potentially invalid. The source's own redraw or reload must reestablish a valid map before use.
3. Keep the unit accumulation region at its actual offset (`+0x2db80` or `+0x3a300`); verify each copied sheet's size before writing.
4. Confirm `LoadCdFile` destination bounds and actual file lengths; disc-sector counts in the static CD table are not decoded lengths or allocation guarantees.
5. Audit special scene / state branches, other `LoadUnits()` call sites and every `SetupField()`/map consumer before claiming the lifetime model is complete.
6. The conservative map-before-unit guard in `source/map_unit_boundary.h` is only an isolated synthetic contract. Its offsets do not prove actual decoded map sizes.

## Next tests

* Add a phase-order model that invalidates a decoded map when a unit file is staged into shared scratch3, and requires successful map reload before map consumption.
* Add a negative test: access to a stale decoded-map view after a staged unit read must be rejected.
* Add a positive test: restored map data becomes consumable again after successful transactional map reload.
* Assess map 39's shifted unit accumulation offset separately.

References: `src/core/main.c` lines 368-434; `src/units/load.c` lines 139-145, 172-186, 209-226; `src/states/game_setup.c` lines 2592-2614; `src/core/cd.c` file destination table.
