# Vandal Hearts USA — owner-local BizHawk replay marker bridge

This follow-up to the *offline* BK2 inspector provides a **manual frame-counter
marker**, not emulation of PS1 gameplay and not MAP02 visual proof.

## Reproduction, strictly owner-local

1. Use a compatible BizHawk installation supporting the **Octoshock** PSX core,
   matching disc/firmware, initial power-on and movie synchronization. Modern
   BizHawk is principally Windows/Linux; Intel macOS is **not** assumed to run
   current EmuHawk. Never upload disc, BIOS, BK2, screenshots or raw console log
   to public GitHub/CI.
2. Generate an *owner-local* inspector report using the following command,
   with output permissions restricted:

   ```bash
   python3 -m tools.inspect_map02_private_bk2 /private/vandalhearts.bk2 > /private/inspection.json
   ```

3. Start the original BK2 in BizHawk read-only playback, verify the core reads
   **PLAY**, then load `tools/map02_bizhawk_private_replay_observer.lua` in the
   Lua console. With J unbound from emulator hotkeys and gamepad controls, press
   J only when observing a potential scene transition. Keep any screenshots or
   GPU/VRAM captures separately **outside** the public checkout.
4. Save the Lua console's marker lines into `/private/markers.txt` without
   uploading them. Validate frame counters locally:

   ```bash
   python3 -m tools.validate_map02_private_replay_markers \
     /private/inspection.json /private/markers.txt
   ```

The observer emits `counter=N candidate_input=N-1` when the BK2 is in PLAY.
This is a **candidate** mapping; the BizHawk emulation frame counter may need
independent offset calibration to the zero-based BK2 input lines. The verifier
checks format, ordering and movie frame bounds, **not** that MAP02 was on
screen. Replaying from savestates, a different core, a mismatch in disc or
firmware, or introducing manual inputs can invalidate timing.

For a real MAP02 witness, visually inspect playback frames and retain private
original-screen screenshots with exact observed emulator frame counters. Verify
movie-to-emulator offset with a known controller event (e.g., the original
recording's first Start press at zero-based **1661**), then cross-reference
source/native capture windows and VRAM evidence. Do not infer MAP02 from input
silence and do not promote a candidate to a verified scene without genuine
emulator display and source/GPU observations.

## Scope and CI privacy

The Lua script does not modify input, save screenshots or open local files; it
prints counter-only markers on a human keypress. The Python verifier reads
owner-local marker text and prior sanitized inspection JSON, suppresses private
paths and unrelated console lines, and emits only marker summary and **false**
provenance flags. It cannot authenticate the retail game/BIOS, verify movie
sync, inspect graphics or establish MAP02 start.

CI uses invented JSON and marker strings only. Parent Draft PR remains
unmerged. This tool is a replay **preparation protocol**, not evidence that
real MAP02 frames have been recorded or that a PS1 emulator ran in CI.
