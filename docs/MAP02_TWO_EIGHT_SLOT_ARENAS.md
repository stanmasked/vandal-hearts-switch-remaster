# MAP02 — two independent eight-slot tactical arenas

This optional asset-free Switch prototype extends Draft PR #270, which already passed all nine GitHub Actions workflows (including genuine NeXium battles). Neither of the two earlier approved **legacy** MAP02 maps nor their generated scene headers are modified. The two expanded arenas are original demonstration data, not PlayStation retail Vandal Hearts MAP02.

## Input behavior and backwards compatibility

- **Minus**: enter the previously verified legacy two-map demonstration. Its L/R controls and game data remain unchanged.
- **ZR** or **L+R**: enter the expanded tactical game; always start at **first arena, 4 allies vs 4 opponents**, identical to the existing NeXium-verified entrance.
- Within the expanded mode, **L**: switch arena A↔B without changing the selected roster size. **R**: switch 4v4 → 3v3 → 1v4 → 4v4 without changing the selected arena. **Y**: restore the current exact combination; **A/B/X/D-pad** retain their already verified tactical meaning.
- The L+R simultaneous chord is handled before either individual shoulder command. Returning to legacy mode still restores its previous independently authored Map 1/Map 2 scenario.

## Second arena content

`data/map02_roster8_second_4v4.json` is an independently authored eight-by-six, asset-free encounter: four allied actors on column 1, four enemies on column 5, and walls at (3,1), (3,2), (3,3) and (4,3). These obstacles create a new pathfinding route but leave a corridor along row 0. The cursor starts at ally (1,0).

`tools/generate_map02_roster8.py --scene secondary --output ...` creates `source/map02_roster8_second_data.h`. The existing default invocation still regenerates the original arena's header **byte-for-byte**. IDs, symbol names, include guards and schema fields are tightly validated to prevent forged source fixtures.

`vh_r8_scene_variant` and `vh_b8_init_scene_variant` validate all six arena/roster combinations. Padded actors have zero coordinates/HP/action flags; invalid indices return without mutating an existing game. Existing `vh_r8_variant` / `vh_b8_init_variant` APIs remain wrappers for the original arena.

## Test and evidence gates

- GCC, Clang and UBSan exercise all six combinations, strict inactive padding, wall avoidance, enemy pursuit and fresh reset through `tests/test_map02_two_eight_arenas.c`.
- `tests/test_map02_two_arena_sources.py` reproduces both C headers byte-exactly, compiles real C from the checked-in fixtures and rejects cross-map IDs, overlapping actors, blocked spawns and duplicate JSON keys.
- A native devkitPro/libnx NRO build with unchanged legacy-scene generator checks is required.
- The new **real NeXium** route enters first 4v4, switches via L to second 4v4, changes via R to second 3v3 and 1v4, moves one allied unit, confirms enemy pathfinding, resets B 1v4, switches to A 1v4, returns to A 4v4, then restores legacy Map 1. It must capture all intermediate states and prove zero pixel delta for resets and the approved old map.
- Existing NeXium battle and map-select workflows must continue to pass.

This is a prototype built from original placeholder data, **not** a full commercial game remake and not a physical Nintendo Switch test. Keep Draft until all CI jobs pass; do not merge stacked branches or upload original game images automatically.
