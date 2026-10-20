# MAP02 — guard state isolation across real Switch scene/roster changes

This independent Draft stage is stacked on the fully tested #295 authored
tactical arena. It changes **no combat rules, original assets, controller
mapping or game renderer**. The parent already proved the READY/ARMED/BLOCKED
cycle in a genuine NeXium session; this child tests unexamined boundaries
where an armed protection state must not leak into a different roster,
arena, restored map or a later enemy phase.

## Controller-only NeXium route

The CI compiles a real NRO using devkitPro, runs all host and sanitizer
checks, then launches NeXium under Xvfb. The driver takes fifteen PNG
screenshots from the emulator window after these actual mapped inputs:

1. Start original MAP02-like battle with MINUS; enter first 8-slot arena
   by L+R; select second arena with L.
2. Arm third-ally guard using A then B; switch to first arena with L.
   The guard label must disappear and first arena board must equal the
   original pixel-for-pixel.
3. Return to second arena with L. Guard must be READY. Re-arm guard.
4. Cycle roster 4v4 → 3v3 → 1v4 → 4v4 with actual R key events.
   Third ally must be visible in 3v3, absent in 1v4; 1v4 must display
   a different unavailable status and 4v4 must restore READY and exact
   original board state.
5. Re-arm, exit expanded mode with L+R, verify the legacy board did not
   change. Re-enter, revisit second arena, verify guard is READY and
   issue a real X enemy phase with no inherited guard; enemy movement
   must visibly alter the board without faking a status change.

Guard comparisons operate in a fixed HUD-only pixel region, separated from
the animated heartbeat. Board comparisons exclude unrelated dynamic UI and
require **zero** differing pixels after the relevant deterministic resets.
Pillow/PNG screenshot checks are not a substitute for actual controller
events, therefore the driver only runs after launching the real emulator.

The exact success marker is:

`VH_MAP02_NEXIUM_GUARD_BOUNDARY_PASS arming=1 scene_reset=1 roster_3v3=1 roster_1v4_unavailable=1 roster_4v4_reset=1 legacy_exit=1 reentry=1 enemy_phase_no_leak=1 first_arena_preserved=1 retail=0`

Three synthetic negative tests fail on blank frames, invalid dimensions and
unchanging hand-drawn allies. Those cases are only adversarial oracle checks,
**not authentic emulator results**.

The NeXium archive is checked against a previously observed Linux release
asset ID 658656899 and SHA-256
`c933fbbcf8d1b011de8d4a79c9d8eb55c0678a305947af9388ddb40ce5960a66`
before extraction. The workflow uploads real screenshots and an execution
log even if the assertion fails, without any private PS1 game image.

Passing this proves only deterministic behavior in the independently
authored Switch homebrew battle. It does **not** prove MAP02 retail
DrawOTag/VRAM parity, original PS1 assets, physical hardware or the
owner-private RU v1.6 BIN identity. Preserve stacked Drafts.
