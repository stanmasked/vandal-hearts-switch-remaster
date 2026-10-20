# MAP02 — opt-in eight-slot roster contract (4 allies + 4 enemies)

## Boundary and scope

This stacked stage follows Draft PR #253 (variable 1–2 active allies/enemies) without changing `source/main.c`, the four-slot `VhMap02Battle` engine, either previously approved JSON map, the generated headers, or the current Switch NRO's player input and graphics. The new `source/map02_roster8.h` is deliberately **opt-in** and **not used by the shipping prototype** until a later migration PR.

An independently authored eight-slot roster uses allies at positions 0–3 and opponents at 4–7, active counts 1–4 per faction, an 8x6 collision grid, and canonical zero padding in absent slots. All authored active units must spawn alive, on distinct unblocked tiles, with their turn action flag cleared. The cursor must start on ally 0. Invalid inputs fail before mutating the destination state.

## Validation and compatibility

- `vh_r8_from_legacy` validates a legacy scenario first, then **copies** its allied slots 0–1 and opposing slots 2–3 into the corresponding new positions, retaining terrain/cursor/HP exactly. Both existing scenes are covered by tests.
- `vh_r8_occupant`, `vh_r8_alive`, `vh_r8_result`, and `vh_r8_attack` demonstrate eight-slot occupancy, living-combatant end states and legal adjacent one-action attacks without touching the existing battle engine.
- Independent 3v3 ally attacks and 4v4 enemy attacks establish non-premature win/loss. Other tests reject duplicate coordinates, blocked tiles, out-of-range counts, hidden forged units, friendly fire and invalid attack distances.
- CI checks GCC, Clang, UBSan and the unchanged devkitPro baseline NRO. A successful baseline NRO check verifies preservation of the existing program, **not playable 4v4 on Switch**.

## Later integration (NOT included)

1. Generalize portable movement/path occupancy and enemy AI to use the expanded side-capacity index contract; preserve four-slot APIs for inherited NeXium tests.
2. Add native scenario generation for 3–4 members per side and actual Switch UI/selection support.
3. Run real NeXium 3v3/4v4 player-input playthroughs alongside the existing MAP 1/MAP 2 controller and screenshot regressions.

No original commercial-game assets or original retail MAP02 data are included or implied.
