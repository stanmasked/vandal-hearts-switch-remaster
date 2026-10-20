# MAP02 — visible guard status on Nintendo Switch

This stage builds on the original asset-free third-ally squad-defense mechanic in Draft PR #289. The player should see whether guard is currently **ready**, **armed** for the next enemy phase, or has **blocked one point of enemy damage**. The game rules, original authored encounter fixtures and input mappings are intentionally unchanged.

## Second arena HUD behavior

Below the existing `ALLY 3 GUARD: B` control legend, the renderer displays one short status label:

- **GUARD READY:** third ally is alive, present in this roster, has a free action, and no protection is active
- **GUARD ARMED -1 HP:** a B guard was issued and is awaiting the next X enemy phase
- **GUARD BLOCKED 1 HP:** the first actual hit in that enemy phase was reduced by one; remains visible through the next player phase
- **GUARD SPENT:** the third ally already acted without an active guard
- **GUARD UNAVAILABLE:** the third ally is absent (notably 1v4) or defeated
- **GUARD FINISHED:** battle already ended

These labels are derived by pure `vh_b8_guard_hud_state` from the current battle and `VhGuard8` states. There is **no guard label on the first expanded arena or the two original MAP02 battles**. Switching L/R, resetting with Y or exiting expanded mode clears the guard-state information using already established behavior.

`source/map02_guard_hud.h` does not mutate or store game data. It gives a compact deterministic UI contract that can be tested separately from the actual NeXium drawing.

## Acceptance gates

- `tests/test_map02_guard_hud.c` checks all six combinations of two arenas and three roster sizes, including no-hit expiration, real absorbed fourth-phase hit, next-phase clearance, spent action, defeated/inactive actor, win/loss, invalid inputs, and unchanged battle memory; GCC, Clang and UBSan run the same host test.
- `tests/test_map02_guard_hud_oracle.py` creates **ten** positive/adversarial synthetic PNG sets, rejecting fake/unchanged HUD transitions and false reset or first-arena appearance. These images are **not actual emulator evidence**.
- `tests/run_map02_nexium_guard_hud.py` drives an actual Switch NRO in NeXium: it records READY, arms guard by real A+B, triggers X for a no-hit expiration, repeats real X turns until the fourth enemy phase, arms again, captures BLOCKED after a mitigated hit, then Y-resets and restores the earlier arenas. PNG comparisons use a HUD-only rectangle avoiding the independently animated frame indicator and must show changed/cleared guard text; patient HP must show a real mitigated loss. Screenshot artifacts and NeXium stdout remain attached to the workflow.
- `.github/workflows/map02-guard-hud.yml` builds a real libnx NRO and requires host rules, 10 forged-image tests, and the genuine NeXium visual result. Changes to `source/main.c` also rerun previously verified MAP02 regressions.

Do not merge this Draft PR until the latest-head NeXium screenshot test and inherited workflows pass. This remains an independently authored placeholder game with no retail PlayStation assets and no claim of physical Nintendo Switch testing.
