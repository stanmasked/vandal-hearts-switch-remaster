# MAP02 — optional four-vs-four Switch homebrew battle (asset-free)

This change stacks on Draft PR #259 (portable 8-slot actions) and PR #256 (validated eight-slot roster), which in turn stack on PR #253. It preserves the already proven original **independent placeholder** two-map tactical fixture and adds a separate eight-unit demonstration. It is not the original retail Vandal Hearts MAP02.

## Controls

1. Start the NRO and press **Minus** to enter unchanged MAP02 battle mode at Map 1.
2. Press **ZR** (on a Switch controller) to enter the separately authored 4 allies vs 4 opponents capacity test. For NeXium's known keyboard mappings, holding **L+R** together also toggles this mode using Q then E.
3. Use D-pad to move the cursor, **A** to select an ally and then choose a legal empty tile or adjacent enemy, **B** to cancel, **X** to end turn (and run opponent AI), **Y** to reset the currently selected mode.
4. Press ZR or L+R again to return to the unchanged two-map demo. On that original mode, individual **L** and **R** still switch the two approved maps. **Minus** switches back to the earlier smoke demo; **Plus** exits.

The 4v4 layout uses independent JSON `data/map02_roster8_4v4.json`, generated source `source/map02_roster8_smoke_data.h`, four allies at x=0 and four opponents at x=1. Each of four adjacent player attacks deals two damage and eliminates one opponent without affecting the other three. The eight-unit renderer draws only living active slots, highlights selected/acted allies, blocks terrain, and shows the tactical status.

## Strict source-to-runtime evidence

`tools/generate_map02_roster8.py` reproduces the checked-in eight-unit header byte-for-byte. CI first verifies the two unchanged source-generated map headers and native legacy tests, builds a real devkitPro/libnx Switch NRO, then runs a new NeXium screenshot assertion `tests/run_map02_nexium_4v4.py`.

The new NeXium route uses actual controller-key input, not direct host-state injection, and must visibly establish:
- legacy Map 1 before entering 4v4;
- four blue allies and four red enemies;
- first foe defeated while three remain;
- four legitimate player attacks ending in victory;
- Y reset restoring the same 4v4 board;
- L+R return restoring the original legacy map pixels.

All screenshots and the NeXium process log are attached to GitHub Actions artifacts. Existing NeXium L/R second-map, five-turn first-map and other regressions triggered by changing `source/main.c` must continue to succeed.

**Verification boundary:** successful NRO compilation is not real emulator validation; only a completed positive NeXium screenshot job confirms actual display and 4v4 runtime inputs. No claim of retail game data, original characters, or physical Switch testing is made.
