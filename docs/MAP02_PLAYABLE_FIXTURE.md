# MAP02 tactical battle fixture — first playable asset-free slice

This is a newly designed, deliberately small original test battle, not an extraction of the original retail Vandal Hearts MAP02 map or game logic. It is a step toward issue #238's playable MAP02 acceptance criterion, not evidence that the retail mission has been ported.

## Controls in the existing libnx Switch NRO

- Press Minus to switch from the original tactical-grid/FT4/CLUT smoke screen into the separate MAP02 battle fixture. Minus again returns to the original screen; existing emulator screenshot expectations should therefore remain unchanged unless the new mode is deliberately entered.
- D-pad moves the cursor; A selects an available ally, moves within two tiles using terrain/occupancy-aware breadth-first search, or attacks an adjacent enemy for one damage.
- B cancels the current selection without consuming the ally's action.
- X ends the player's turn; each living opponent deterministically attacks an adjacent ally or advances one legal cell toward the nearest reachable ally. Allied actions reset after the enemy phase.
- Y restarts the same deterministic fixture, including its cursor, actor coordinates and HP. Plus exits the NRO.

## Implemented portable C11 battle rules

The independent header-only 8x6 state machine contains 2 allies and 2 enemies, blocked terrain, a shortest-path BFS that respects obstacles and living actors, per-unit action flags, deterministic enemy turns, HP damage, win/loss detection and replayable initialization. It is compiled into the same existing source/main.c NRO, but does not replace the existing legacy mode and remains free of original game data.

tests/test_map02_battle_fixture.c covers initialization, obstacles, inability to cross walls or occupied cells, legal and illegal selection, ally action gating, range checks, turn replay determinism, actual adjacent attacks, victory/defeat and enemy movement that never enters blocked terrain or overlaps another living actor.

Portable GCC/Clang CI and the devkitPro libnx NRO build must both pass before calling this step confirmed. A physical Nintendo Switch run, NeXium gameplay screenshot and original retail mission remain outside this stage's evidence.

## Next acceptance requirements

Add a distinct NeXium interactive smoke which enters the mode with Minus and verifies at least one real D-pad/A movement, X enemy turn, and Y reset in screenshots. Then extend the battle model to data-driven actors/map and a real battle-completion transition. Only after that attempt mapping any legally supplied original game material to the scene. Do not publish private ROM, screenshots exposing private content or proprietary source data.
