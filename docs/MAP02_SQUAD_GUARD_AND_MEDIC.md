# MAP02 — optional third-ally squad guard and medic cooperation

This is a new, independent, **asset-free** tactical combat ability for the Nintendo Switch homebrew prototype. It is not an extracted PS1 Vandal Hearts skill and no retail image or proprietary game assets are included.

## Scope and controls

In the optional expanded **second** 8-slot tactical arena only, the third allied unit (slot 2, initially tile 1,2) may spend its action to issue a one-turn squad defense order. Press **A** on that ally, keep the cursor on the same tile, then press **B**. The **first enemy attack in the next opponent phase** deals **one less HP** (2→1 in the current prototype), regardless of which living ally is struck. The shield expires after that one opponent phase, even if no attack lands, and cannot be stacked or used twice by the same unit that turn. Ordinary enemy target selection, shortest-path movement, tie breaks and all subsequent enemy attacks remain unchanged.

The medic (second allied unit) can subsequently heal a living injured adjacent ally with its existing A/B support action (up to 2 HP, cap 3); the archer's 2–3 tile B attack, conventional A melee/movement, default B cancel, X end turn, Y restart, L/R stage/roster selection and ZR/L+R mode toggles remain as already NeXium-verified. The first expanded arena and both old approved authored MAP02 fixtures do not enable guard. The 1v4 roster has no third ally, so no guard is available. On stage changes, roster changes, Y restart or leaving/entering expanded mode, the guard state is reset.

## Source and engine correctness

`source/map02_guard8.h` introduces opt-in `VhGuard8`, `vh_b8_guard_action` and `vh_b8_end_turn_guarded`. Guarded enemy AI uses the **same deterministic BFS and target-selection algorithm** as `vh_b8_end_turn`. Without an active defense, its call delegates exactly to the original unmodified AI. With defense, the first adjacent attack has its damage reduced by precisely one, and all other enemy actions are identical. Invalid guard commands leave both game and guard state unchanged.

`tests/test_map02_guard8.c` tests no-op invalid commands, one action per ally per turn, one-turn expiry, default enemy AI parity, a real unchanged portable enemy encounter (original hit 2HP versus guarded 1HP), and successful medic restoration afterward. GCC, Clang and UBSan all run this original-data-free model. No existing legacy model files are modified.

`tests/test_map02_guard_oracle.py` supplies **15** synthetic complete/missing/forged screenshot sequences that the oracle must accept/reject correctly. These deliberately synthetic fixtures do not prove real emulator playback.

`tests/run_map02_nexium_guard.py` requires a real devkitPro/libnx Nintendo Switch NRO running in NeXium, driven exclusively with keyboard-mapped controller inputs. It plays three real AI approach phases, records the unguarded fourth-phase attack, then resets the arena and replays exactly the same three phases. It commands ally slot 2 to guard using real A and B presses, triggers the fourth enemy phase, and measures the before/after health-bar pixels of the attacked first ally. Then the medic must heal that same actual wound using A/B. Genuine PNG evidence must also establish that the third ally spent its action, that all actions reset after the opponent phase, and that both resets, original expanded arena and approved legacy MAP02 are restored with **zero changed board pixels**.

`.github/workflows/map02-guard-stance.yml` holds the separate GCC/Clang/UBSan, adversarial screenshot, native NRO and real NeXium acceptance gates. Existing map, victory, AI, archer and medic NeXium routes run unchanged. **Keep Draft until all checks complete.** No physical Switch operation is claimed.
