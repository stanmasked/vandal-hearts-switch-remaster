# MAP02 full battle — deterministic player-controlled victory fixture

This test complements PR #241 (playable asset-free tactical mode) and issue #238. All its actions go through the same vh_bchoose(), vh_bend_turn() and vh_binit() APIs that the libnx Switch NRO uses for A, X and Y. No unit, HP, turn counter or status is modified by the test after normal vh_binit(). The test is independent of the PS1 retail game.

## Concrete five-turn solution from the original starting state

The initial 8×6 board places allies (1,2) and (1,4), and enemies (5,2) and (6,4), with the original authored prototype obstacles.

- Turn 1: ally 0 walks to (1,0); ally 1 walks to (3,4); let both enemies move.
- Turn 2: ally 0 walks to (3,0); ally 1 walks to (4,5); let both enemies move.
- Turn 3: ally 1 attacks enemy 3; ally 0 waits; let enemies respond.
- Turn 4: ally 0 attacks enemy 2; ally 1 defeats enemy 3; let remaining enemy respond.
- Turn 5: ally 0 defeats enemy 2, producing VH_BWIN without a fifth enemy phase.

Assertions establish terrain/collision integrity after every phase; four legal movements, four adjacent melee attacks, four genuine AI phases, the loss of all enemy HP, living allies, no further actions after victory and a full reset to the exact original starting state. Execute the complete battle twice and compare each phase byte-for-byte for deterministic replay.

This is a non-retail gameplay proof at the shared portable battle-state API level. The NeXium input/image pipeline in separately stacked PR #243 is a different acceptance step; neither claims that Vandal Hearts retail MAP02 has been reproduced or that a physical Switch was tested.
