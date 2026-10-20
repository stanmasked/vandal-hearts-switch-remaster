# MAP02 — data-driven authored tactical encounter

This step follows the successful asset-free five-turn victory in real NeXium on [PR #247](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/247). It **does not** import or reproduce the retail PS1 MAP02 level. The encounter is still an original test fixture.

## Authoring and build-time loading

- `data/map02_fixture.json` is the single human-readable encounter description: board dimensions, blocked cells, two allies, two enemies, starting cursor, movement range, attack damage and two outcome-event rules.
- `tools/generate_map02_fixture.py` validates a strictly whitelisted JSON schema and generates the portable `source/map02_encounter_data.h` embedded by the NRO. It refuses duplicate keys, out-of-bounds or duplicate cells, units on walls, bad HP, changed dimensions, unsupported fields and missing or contradictory events.
- `python3 tools/generate_map02_fixture.py --check` fails if the committed C header is stale or modified. To intentionally update an authored fixture, change JSON, then rerun without `--check`, execute all tests, and verify full NeXium screenshots.
- There is **no runtime access to original disc content** and no claim that the file is an authentic MAP02 extraction. Runtime gameplay loads the validated *compiled* scenario; original console gameplay remains unverified.

## Game engine consumption

The portable C11 `source/map02_battle_fixture.h` now initializes `VhMap02Battle` through `vh_binit_scenario()`, with validation completed before modifying the live state. Terrain collision and NeXium renderer read the active scenario wall bitmap; HP and positions use the authored unit spawns. Movement range and per-attack damage are configured rather than literal values. The win/loss evaluation loops through two authored, type-checked battle events:

- `all_enemies_defeated -> victory`
- `all_allies_defeated -> defeat`

The `vh_binit()` public entry point and Minus/Y controller flows still select the original authored fixture. The legacy `vh_bwall()` query remains for compatibility with existing unit tests, while actual gameplay uses `vh_bwall_at(state, x, y)`.

## Acceptance proof

`tests/test_map02_encounter_data.py` verifies deterministic generation, stale-header detection and malformed input refusal. `tests/test_map02_data_driven.c` verifies the previous default scene remains identical, a distinct authored layout changes terrain and BFS movement, a configurable two-damage attack takes effect, the outcome events work irrespective of order, and invalid scenario loading leaves existing state unchanged.

The independent GCC/Clang matrix in `.github/workflows/map02-data-driven.yml` executes both test suites and the original `test_map02_battle_fixture.c`. The inherited NeXium full-victory workflow must additionally pass on this commit, demonstrating that the complete existing five-turn input path and framebuffer output remain intact when source data is moved out of the battle engine.

**Next step:** add multiple authored encounter definitions and select by scenario ID, then support private, user-authorized game-material ingestion through local tooling without ever publishing proprietary files. Real retail MAP02 scene fidelity and physical Nintendo Switch behavior are distinct acceptance gates.
