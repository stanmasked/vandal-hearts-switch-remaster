# Tactical rules test results

**Status:** confirmed by GitHub Actions on 2026-10-14.

## Evidence

- Exhaustive grid and movement checks: [run 38612492280](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38612492280) — passed.
- Invalid-origin and negative-range checks, plus NRO build: [run 38612889792](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38612889792) — passed.
- Runtime smoke test for the updated libnx NRO: [run 38612865828](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38612865828) — build and NeXium runtime job passed.

## Covered rules

The host-side tests exercise:

- Manhattan distance and grid bounds;
- cursor clamping for all 48 grid positions and all nine combinations of direction deltas (-1, 0, 1);
- movement range across every cell on the 8×6 board;
- enemy-cell blocking;
- rejection of destination coordinates outside the board;
- rejection of source coordinates outside the board;
- rejection of negative movement range;
- selection, cancellation, successful movement, and rejected movement without unintended hero-position changes.

## Limitations

These are tests of the standalone tactical prototype's rules, not of the original Vandal Hearts game logic. NeXium success is emulator evidence only; physical Nintendo Switch behavior is not yet confirmed.

The separate SDL2 feasibility workflow remains blocked before compilation because the devkitPro package database returns HTTP 403. Its failure is not evidence that the SDL2 probe itself fails to compile or run. See [run 38612865771](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38612865771).
