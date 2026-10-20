# MAP02 — selectable 4v4, 3v3 and 1v4 Switch tactical rosters

## Scope

This is an isolated feature stage on top of the already verified optional asset-free 4v4 homebrew in Draft PR #265. The two existing approved authored MAP02 scene maps, their legacy controller routes and retail asset privacy remain untouched. This does not reconstruct retail PlayStation Vandal Hearts MAP02.

## Nintendo Switch controls and invariants

- **Minus** enters the original two-map battle demonstration.
- **ZR** or **L+R** enters the expanded battle; it always starts with the previously verified **4 allies versus 4 opponents**.
- While in that expanded mode, press **R** to cycle 4v4 → 3v3 → 1v4 → 4v4. This changes the battle to a newly validated *fresh* composition, resetting selection, turn counter, cursor, HP, and all actor action flags. The board artwork and original independent 4v4 JSON positions are retained.
- **A** selects/moves/attacks; **B** cancels; **X** ends a turn; **Y** restarts the *currently selected* composition; **ZR** or **L+R** returns to the unchanged two-map mode. An L+R simultaneous toggle cannot accidentally invoke an R-only roster change because the controls test the chord first.

`source/map02_roster8_variants.h` copies the independently authored 4v4 fixture. For 3v3, it zeroes the fourth actor on each side. For 1v4, it zeroes only allied slots 1–3. Zero HP, coordinates and acted state are mandatory in every padded slot. Invalid variant IDs reject without modifying live battle data.

## Required independent evidence

`tests/test_map02_roster8_variants.c` covers all three active counts, padding, selection, a real legal attack and Y-equivalent restarts, as well as invalid-ID rejection without mutation. It runs under GCC and Clang, plus UBSan.

`tests/test_map02_roster_variants_oracle.py` provides 11 synthetic valid/corrupt screenshot sets to check that the real screenshot oracle rejects forged fourth actors, absent enemies, false melee, incorrect reset or roundtrip, unchanged labels and invalid dimensions. These synthetic frames **do not prove the emulator**.

`tests/run_map02_nexium_roster_variants.py` then controls a real Switch NRO inside NeXium exclusively using mapped keyboard-to-controller inputs. It captures original Map 1, default 4v4, 3v3, 1v4, real one-ally attack, Y reset in 1v4, wraparound 4v4 and legacy restoration. Exact board pixel equality is required for reset and return. Screenshots and a process log are uploaded as GitHub Actions artifacts.

The native NRO build and each inherited MAP02 NeXium regression must pass before considering this control extension verified. Keep the PR Draft until real NeXium visual evidence is positive, and never merge or upload the retail game image automatically.
