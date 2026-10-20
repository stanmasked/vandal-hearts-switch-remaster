# MAP02 — optional second-arena field medic

This stage extends the independently authored, asset-free Switch tactical prototype in Draft PR #281. It does not claim recovery of any retail PlayStation Vandal Hearts abilities or stats.

## Player controls

The second active allied unit (slot 1) is a support medic **only in the optional second 8-slot arena**.

- Select the medic with **A**, move the cursor onto a **living, injured, directly adjacent ally** and press **B**. The medic heals up to **2 HP**, capped at the authored maximum of **3 HP**, then spends that player's action. The medic cannot heal themselves, dead allies, enemies, teammates at a diagonal or distance greater than one, or take two support actions in a turn.
- In that second arena, **B on a full-health ally** retains the pre-existing cancel behavior; **B on an injured but out-of-range ally** rejects the support attempt without consuming the turn or canceling selection.
- The first allied unit's existing 2–3-cell archer shot (A select → B on distant enemy) is untouched; B on empty tiles cancels as before. The first arena, 4v4/3v3/1v4 selection, L scene switching, X enemy phase, Y restart and two older legacy MAP02 scenarios retain their existing behavior.
- In 1v4 the medic slot is inactive; no invisible extra ally is spawned and no heal is available.

## Independent correctness and security gates

`source/map02_medic8.h` is portable header-only ISO C, with zero mutation for all rejected heals and a separate return marker `VH_BHEAL`. No saved game state, authored JSON, enemy movement rules, or original game resource is modified.

`tests/test_map02_medic8.c` checks full-health rejection, a legal heal from 1→3 HP and 2→3 HP, spent actions, no resurrection, no self/enemy/diagonal healing, no repeated support, invalid pointers, inactive roster slots, preserved source maps, and **a real portable enemy AI phase** damaging an ally before a support action. GCC, Clang and UBSan enforce the behavior.

`tests/test_map02_medic_oracle.py` contains 13 synthetic positive/negative frame scenarios, rejecting nonexistent damage, fake healing, over-healing, unused medic, false reset or first-map restoration. These deliberately synthetic images **are not evidence of actual emulator gameplay**.

`tests/run_map02_nexium_medic.py` drives an actual NeXium session with keyboard-mapped controller actions: enter original MAP02, enable the expanded 4v4, select arena B, reject a heal on a healthy teammate, then trigger independent enemy turns by X until the first ally suffers real visible damage. It selects the medic using A and heals the patient with B; authentic PNGs must demonstrate increased health-bar pixels, the medic's spent-action color and zero-difference restoration of the arena, earlier scene and legacy MAP02. The script bounds enemy turns to eight and refuses dead patients or unobserved injury.

`.github/workflows/map02-field-medic.yml` builds a real devkitA64/libnx NRO and requires both the real NeXium proof and all previous MAP02 regressions. Keep the PR Draft until these have actually passed. Do not commit or upload private retail PS1 game images.
