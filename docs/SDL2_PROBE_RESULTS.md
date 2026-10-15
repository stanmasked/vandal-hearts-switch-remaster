# SDL2 Switch feasibility probe results

## Latest run

The latest confirmation is run [38694397097](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694397097), commit [8c397a3](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/8c397a3ebef64da66add5fc84d870eeba63f499e). It additionally verifies that rejected invalid frame metadata leaves the active frame dimensions unchanged. Runtime evidence: [artifact 11954141491](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694397097/artifacts/11954141491).



The latest SDL2 feasibility workflow completed successfully on 2026-10-15:

- Workflow run: [38694397097](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38693397077)
- Branch: `audit/switch-platform-boundaries`
- Commit tested: [8c397a3ebef64da66add5fc84d870eeba63f499e](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/74b903662b0956b10514f27c8565ed58d6659c6e)
- Build job: successful; official SDL2 2.28.5 source was downloaded, checksum-verified, patched for the Switch port, compiled, and installed in the CI toolchain.
- Runtime job: successful in the NeXium emulator.
- Runtime evidence: [sdl2-nexium-runtime-evidence artifact](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38693397077/artifacts/11954141491)

## Confirmed checks

- SDL2 texture and joystick probe: 1280×720 screenshots captured; A toggled the movement-range highlight, B canceled it, and two Right presses moved the cursor from tile (1, 2) to (3, 2).
- RGB24 texture upload with an odd source stride: all four expected color/orientation markers were detected in the rendered viewport.
- Repeated per-frame RGB24 upload: two screenshots taken 0.75 seconds apart showed the animated patch changing, confirming visible updates while the NRO loop repeatedly uploads and draws frames.
- Optimized steady-state uploads: the presenter allocates texture storage with `glTexImage2D` on first upload/resize and uses `glTexSubImage2D` for same-sized subsequent frames. The optimized build and repeated-update screenshot check passed.
- Resize round-trip: the probe uploaded a 17×9 frame, restored the original 321×240 frame, checked the presenter dimensions, and continued drawing successfully.
- Invalid-metadata recovery: the presenter rejected an invalid frame without changing the dimensions of the last valid frame; the updated runtime workflow passed.
- SDL2 software renderer: expected generated hero and enemy markers detected in the screenshot.
- SDL2 OpenGL ES 2.0: expected generated hero and enemy markers detected in the screenshot.
- The runtime artifact includes captured screenshots and logs. Other artifacts include the built software-renderer, GLES, texture-upload, RGB24 and audio probe NROs.

## Audio result: inconclusive, not a pass for playback

The audio step completed under the workflow's documented inconclusive-result rule. Its log reports ALSA `cannot find card '0'` and `Unknown PCM default`; the CI host has no usable default audio device. The screenshot status classifier did not confirm an observed SDL audio callback. This run does **not** establish callback execution, audible output in NeXium, or sound on physical Switch hardware.

## Limits and next steps

These are isolated platform-feasibility probes, not integration of the Vandal Hearts PC port. They validate SDL2 rendering, OpenGL ES context/output, CPU-framebuffer texture upload, and controller-event handling in an emulator environment. They do not prove that the upstream game's renderer, assets, audio engine, file I/O, or full gameplay already work on Switch.

Next engineering step: audit the upstream PC port's renderer and dependency boundaries against these confirmed Switch capabilities, then select one small integration seam for a testable porting spike. Audio remains a separate open issue until a supported audio backend produces stronger runtime evidence.
