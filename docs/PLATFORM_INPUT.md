# Platform-neutral input contract

## Purpose

`source/platform_input.h` is the seam between native platform input and the tactical game state. A platform adapter translates device-specific button events into the `VH_INPUT_*` bit flags. The game-state functions do not need to know whether an action came from libnx, SDL, keyboard input, or a test.

## Current action mapping

| Action | Current Switch button | Effect |
| --- | --- | --- |
| `VH_INPUT_LEFT` | D-pad Left | Move cursor one cell left |
| `VH_INPUT_RIGHT` | D-pad Right | Move cursor one cell right |
| `VH_INPUT_UP` | D-pad Up | Move cursor one cell up |
| `VH_INPUT_DOWN` | D-pad Down | Move cursor one cell down |
| `VH_INPUT_CONFIRM` | A | Select the hero or attempt a move |
| `VH_INPUT_CANCEL` | B | Clear hero selection |
| `VH_INPUT_QUIT` | Plus | Exit the prototype loop |

## Processing rules

- Actions are bit flags, so a frame can report more than one action.
- Quit is checked first. If present, `vh_process_input` returns nonzero without applying gameplay actions.
- Directional actions are processed in Left, Right, Up, Down order; each movement is clamped to the board.
- Confirm is processed after directional movement. Thus a frame containing Right + Confirm moves the cursor first, then confirms at its new cell.
- Cancel is processed after confirm, so Cancel clears selection if both are present.
- The function returns zero when the caller should continue, and nonzero when the caller should leave the main loop.

## Verification

Host-side tests include this header without including `switch.h`. This keeps the action/state contract testable in ordinary CI without a Switch SDK or emulator. The Switch application still performs native button polling in `source/main.c`; only the translation to game actions is platform-specific.

## Scope and limitation

This layer is an architectural seam, not a port of the original game's controls. The current application remains a generated tactical-grid prototype. A future port must map the original game's actual input semantics and menus rather than assuming this prototype mapping is equivalent.
