# SDL2 Switch feasibility probe results

## Latest run

The SDL2 feasibility workflow completed successfully on 2026-10-15:

- Workflow run: [38691365198](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38691365198)
- Branch: `audit/switch-platform-boundaries`
- Commit: `41087dd3e060cfafbca6995cde8e698bea59aefd`
- Build job: successful; official SDL2 2.28.5 source was downloaded, checksum-verified, patched for the Switch port, compiled, and installed in the CI toolchain.
- Runtime job: successful in the NeXium emulator.
- Runtime evidence: [sdl2-nexium-runtime-evidence artifact](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38691365198/artifacts/11951579038)

## Confirmed checks

- SDL2 texture and joystick probe: 1280×720 screenshots captured; A toggled the movement-range highlight, B canceled it, and two Right presses moved the cursor from tile (1, 2) to (3, 2).
- RGB24 texture upload with an odd source stride: all four expected color/orientation markers were detected in the rendered viewport.
- SDL2 software renderer: expected generated hero and enemy markers detected in the screenshot.
- SDL2 OpenGL ES 2.0: expected generated hero and enemy markers detected in the screenshot.
- The CI artifact archive includes runtime screenshots and logs.

## Audio result: inconclusive, not a pass for playback

The audio step completed under the workflow's documented inconclusive-result rule. Its log reports ALSA `cannot find card '0'` and `Unknown PCM default`; the CI host has no usable default audio device. The screenshot's status-color classifier did not confirm an observed SDL audio callback. Therefore this run does **not** establish callback execution, audible output in NeXium, or sound on physical Switch hardware.

## Limits and next steps

These are isolated platform-feasibility probes, not integration of the Vandal Hearts PC port. They validate SDL2 rendering, OpenGL ES context/output, CPU-framebuffer texture upload, and controller-event handling in an emulator environment. They do not prove that the upstream game's renderer, assets, audio engine, file I/O, or full gameplay already work on Switch.

Next engineering step: audit the upstream PC port's renderer and dependency boundaries against these confirmed Switch capabilities, then select one small integration seam for a testable porting spike. Audio remains a separate open issue until a supported audio backend produces stronger runtime evidence.
