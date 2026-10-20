# MAP02 — flexible active troop counts (within current four-slot prototype)

This step builds on the verified two-map Switch tactical prototype [PR #252](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/252), where both independently authored maps can be selected with L/R and defeated through real NeXium controller inputs. No original Vandal Hearts retail content is used.

## Problem removed

The original portable model required exactly two allies and two opponents in every scenario. The same map and movement engine can now validate and execute **one or two active allies and one or two active enemies**, in any of four combinations. The four physical array slots remain fixed as positions [ally0, ally1, enemy0, enemy1], but unused slots must be exactly zero (0,0,0,0), and are never selected, attacked, rendered, moved or included in victory/defeat checks.

- Both existing data files keep their original two-on-two rosters and exact terrain/rules. Their generated headers add canonical active counts `2, 2`; game actions and the existing MAP 1/MAP 2 NeXium screenshots must remain unchanged.
- `tools/generate_map02_fixture.py` accepts only one or two actors in each JSON `allies`/`enemies` roster, emits a canonical zero-filled padding slot and validates every active position, HP and identity. The existing approved fixture IDs remain the only accepted IDs.
- `vh_bscenario_valid()` refuses zero/oversized counts, nonzero hidden padding and invalid spawns or cursor. `vh_binit_scenario()` performs this validation before changing any live game data.
- `vh_bchoose()`, `vh_bend_turn()` and `vh_bupdate_status()` now respect active troop counts, so a single ally can win against a single foe by an actual adjacent attack, while a remaining second opponent prevents premature victory.

## Regression and acceptance gates

`tests/test_map02_variable_rosters.c` checks real gameplay in the 1-vs-1, 1-vs-2 and 2-vs-1 configurations, plus inherited 2-vs-2 maps. Nine deliberate corrupt-count and hidden-unit variants must be rejected with bit-identical game state.

`tests/test_map02_variable_rosters.py` checks the JSON compiler's padding and rejection behavior and byte-for-byte identity of both previously approved generated data headers.

The dedicated GCC/Clang matrix compiles each gameplay test independently and builds the real devkitPro/libnx NRO. Inherited full-battle NeXium on Map 1 and second-scene NeXium on Map 2 still must pass to confirm no controller/graphics regression.

**Limit:** this only removes mandatory 2+2 occupancy within a **maximum of two allies and two opponents**; a future planned stage will enlarge total party capacity and provide multi-actor turn UI. It is not a retail Vandal Hearts mission reconstruction or a physical Switch verification.
