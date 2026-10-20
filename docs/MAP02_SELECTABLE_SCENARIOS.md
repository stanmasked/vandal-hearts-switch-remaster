# MAP02 — two selectable, original, asset-free battle scenarios

This feature stacks on the fully tested data-driven default battle [PR #250](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/250). Both maps are original fixtures for Nintendo Switch homebrew development. Neither reproduces the original retail Vandal Hearts PS1 MAP02 mission.

The authored data is stored in two explicit JSON source files:

- `data/map02_fixture.json`: **Map 1**. Its original 8×6 four-unit scene remains byte-identical, preserving the proven five-turn full victory in NeXium.
- `data/map02_fixture_b.json`: **Map 2**. A distinct 8×6 arrangement with two nearby opponents, additional wall cells, move range 3 and attack damage 2. Each hero can defeat one enemy in a legal adjacent attack, yielding a fully playable two-attack victory. No game-owned assets are used.

The restricted `tools/generate_map02_fixture.py` translates only the two approved IDs to two deterministic headers: `source/map02_encounter_data.h` and `source/map02_encounter_b_data.h`. `--all --check` must match both headers byte-for-byte; unknown/retail IDs and ill-formed content are rejected. This is validated source generation at build time; it is **not** arbitrary runtime JSON loading on Nintendo Switch.

## Switch controls

1. Minus opens the existing first battle as before (ensuring all original NeXium screenshot and five-turn replay tests remain valid).
2. L or R switches between **MAP 1/2** and **MAP 2/2**, resets the game to the selected map, and redraws terrain, actor positions and HP.
3. D-pad + A perform normal selection/movement/melee, X runs the enemy phase, and Y resets the **currently selected** scenario. Minus closes the optional battle mode.

NeXium's public default controller configuration maps L to **Q** and R to **E**. Real in-emulator input verification of the new map-selection keys is a separate acceptance gate; the earlier default-map NeXium proof does not by itself prove the second scene was selected in the emulator.

## Acceptance tests

`tests/test_map02_two_scenarios.py` validates both JSON files, corresponding C header bytes, approved IDs, input/refusal behavior and Switch selector wiring.

`tests/test_map02_two_scenarios.c` confirms both map IDs, different walls/actors/rules, fail-closed invalid indices, deterministic selection/reset and a **legitimate two-attack victory** in Map 2 via `vh_bchoose()` with no HP/position manipulation. Existing default scenario tests and the 5-turn NeXium full victory run unchanged.

The dedicated CI matrix builds with GCC and Clang and real devkitPro/libnx NRO. Existing project workflows and full NeXium default-map replay are also expected to pass before promoting the PR from Draft.

This is incremental proof for an authored prototype, not a recreation of the commercial PS1 game or a physical Switch playtest.
