# MAP02 — optional line-of-sight archer ability (second arena only)

This is an original, asset-free Switch tactical prototype, stacked on verified Draft PR #273. It is **not** an assertion that an archer skill has been recovered from the original commercial PlayStation Vandal Hearts game.

## Controls and compatibility

In the expanded (ZR or L+R) mode, select **Arena B** with L. The first allied unit (slot 0) can perform a straight-line **bow attack across two or three tiles**. Press **A** on that ally to select it, move the cursor over a living enemy, then press **B** to fire. The bow deals 2 HP of damage and consumes the archer's single action for that turn. A subsequent X enemy phase clears action flags in the ordinary way.

The attack requires that the target is in the same row or column and that all intervening cells are free of walls **and living units**; diagonal attacks, walls, friendly fire, dead targets, allies who already acted, range 1 and range greater than 3 are rejected without mutating any battle state. For a selected archer aiming at an enemy at an invalid range, B leaves selection intact so a mistake cannot spend an action or silently cancel. **B on an empty/friendly square still cancels**; ordinary A melee/movement, Y reset, L/R scene/roster selection and ZR/L+R toggling are unchanged. Arena A and both approved legacy MAP02 maps retain all their original behavior.

For the original second map, the archer starts at (1,0), while the first enemy is at (5,0), **outside** bow range. Only after a legal advance to (2,0) and an enemy phase placing that foe at (4,0) does the archer get a valid, clear two-square shot via B. The new native HUD on Arena B reads `ALLY 1 BOW: B`.

## Tests and acceptance evidence

- `source/map02_ranged8.h`: bounded cardinal ray-cast and fail-closed state mutation API, wholly separate from the original four-unit MAP02 engine.
- `tests/test_map02_ranged8.c`: exact portable sequence plus rejected four-square shot, blocked walls, obstructing actors, diagonal/friendly/adjacent shots, used action, eliminated target, no mutation on invalid input, one-enemy remaining state, last-enemy victory and exact original source-map data preservation. GCC, Clang and UBSan gates.
- `tests/test_map02_bow_oracle.py`: 12 synthetic valid/forged screenshot cases checking blocked attempts, preserved selection, enemy approach, one real shot, other surviving foes, reset and untouched arenas. Synthetic frames alone are **not real NeXium evidence**.
- `tests/run_map02_nexium_bow.py`: real NeXium mapped D-pad/A/B/X/Y/L input and PNG captures, requiring an out-of-range B shot to be rejected, a real 2-square shot to eliminate one opponent, and unchanged scene A and legacy MAP02 pixels after reset.
- `.github/workflows/map02-ranged-shot.yml`: independent native C compiler gate, source/image oracle, devkitPro/libnx NRO build, genuine NeXium screenshot route and evidence artifact.

This remains a stacked Draft PR until its own and inherited MAP02 workflows complete successfully. The repository must not include retail PS1 source-image data, and a successful emulator run does not establish operation on a physical Switch.
