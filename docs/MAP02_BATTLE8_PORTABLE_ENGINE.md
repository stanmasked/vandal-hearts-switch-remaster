# MAP02 — independent portable 4+4 tactical turn engine

This stage is stacked on the eight-slot roster contract in Draft PR #256, and therefore on the variable 1..2 unit model in Draft PR #253. It adds an **opt-in host/portable engine**, `source/map02_battle8.h`, without changing `source/main.c`, `VhMap02Battle`, the two approved authored maps, or their generated headers.

## Implemented portable rules

- Eight physical positions: allies 0–3, opponents 4–7. Active counts can be 1–4 independently per side, using the validated `VhRoster8` contract.
- `vh_b8_init` validates all spawn data and move/attack parameters before replacing any live state.
- `vh_b8_path` uses bounded breadth-first search on the existing 8x6 grid. Blocking terrain and living actors are impassable; only the explicitly identified AI target can be a terminal occupied square.
- `vh_b8_choose` selects a living, not-yet-acted ally, then allows either a legal empty-tile move within the configured path length or an adjacent attack against an active enemy.
- `vh_b8_end_turn` gives every surviving opponent one attack or one unoccupied-tile step toward the nearest reachable living ally; it checks game end states after damage, resets acted flags and increments the turn counter.
- Victory/defeat are based on all active, living units, not on a fixed pair of heroes or enemies. Inert and eliminated units cannot be selected as actors.

## Verifiable tests

`tests/test_map02_battle8.c` exercises a 4v4 player-action victory, a 4v4 enemy-phase defeat, a 1v2 two-turn victory, a 2v1 multi-turn enemy victory, collision and pathfinding around blocked terrain, and invalid-init preservation of a live state. CI compiles the portable tests independently on GCC and Clang with UBSan, reruns previous two-scenario/variable-roster tests, validates the unchanged generated map headers and rebuilds the existing Switch NRO.

## Important limitations

**This does not yet put 4v4 controls, animations, pathfinding or battles into the Nintendo Switch NRO or the NeXium emulator.** A passing native NRO gate only verifies that the existing 2+2 demo remains buildable. No retail MAP02 scene or game content is represented here.

To make this feature visible on Switch in a later isolated stage, the native entry point must explicitly adopt this new battle state, load a verified independent 3–4-unit authored fixture, display each active slot, handle controller movement and selection, and complete new end-to-end NeXium victory and loss tests. The existing NeXium routes must continue to pass before any default-mode change.
