# Switch platform-boundary audit

## Purpose

Track the platform-specific work required before integrating the upstream Vandal Hearts PC port. This is an engineering checklist, not evidence that the original game already runs on Switch.

## Confirmed facts from the current project audit

- The upstream PC port separates the matching game decompilation from the native C platform layer under `platform/pc/`.
- The desktop build uses SDL2 for window/input, OpenGL on Windows/Linux (including legacy pixel-presentation calls), and an SDL Metal renderer on macOS.
- The PC backend uses OpenAL for audio and a threaded rasterizer; its bootstrap contains Windows, POSIX, and macOS-specific memory/executable handling.
- The upstream presentation contract was source-audited at commit `14552fffa0e0b47e02b57592e274fc6e7a649923`: packed RGB24, tightly packed `width * 3` stride, bottom-up rows, RGB channel order, and 5-bit channel expansion by bit replication. The scratch buffer is call-scoped and must be consumed/copied before the presenter returns.
- The SDL2 feasibility workflow [38644241528](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38644241528) built five NRO probes from pinned SDL2 source and passed NeXium checks for joystick input/texture presentation, odd-stride RGB24 texture upload, SDL2 software rendering, and OpenGL ES runtime.
- That same run's audio check completed as **INCONCLUSIVE** when the CI environment reported no usable ALSA default device. A green workflow result is not evidence of an executed SDL audio callback or audible output in this environment.
- The separate libnx prototype verifies cursor movement and basic selection/movement rules in NeXium. Physical Switch behavior, graceful exit, sustained sessions, and audible audio remain unverified.
- The upstream audit was performed against commit `14552fffa0e0b47e02b57592e274fc6e7a649923`; re-audit the upstream revision before implementation if the dependency changes.

## Required boundary inventory

### Presentation

- [x] Trace the upstream framebuffer format, dimensions, stride, orientation, and scaling from rasterizer output to presentation.
- [x] Identify legacy desktop presentation calls unavailable in GLES2, including `glDrawPixels`, `glPixelZoom`, and `glRasterPos2f`.
- [x] Define and host-test a frame view contract for packed RGB24, stride, bounds, and bottom-up row access in `source/rgb24_frame.h`.
- [x] Add and host-test centered aspect-preserving destination-rectangle calculation in `source/switch_presenter_layout.h`.
- [ ] Implement a Switch presenter adapter for the upstream frame without changing the byte-matching game source.
- [ ] Compare that adapter against a known desktop frame for orientation, color channels, scaling, filtering, and letterboxing.
- [ ] Confirm sustained frame updates and clean shutdown on target hardware.

### Input

- [ ] Trace the upstream keyboard and `SDL_GameController` paths and identify the smallest platform-specific adapter boundary.
- [ ] Test Switch SDL joystick events or libnx pad polling on physical controllers.
- [ ] Verify every action, repeated presses, edge clamping, cancellation, and clean exit.

### Bootstrap, memory, and filesystem

- [ ] Inventory Windows `VirtualAlloc`/`VirtualProtect`, POSIX `mmap`/`mprotect`, and macOS Mach-O/dyld assumptions in the bootstrap.
- [ ] For each behavior, record why the game requires it and identify a Switch-supported equivalent before replacing it.
- [ ] Determine paths for user-provided disc data, generated files, configuration, and saves without embedding proprietary game data in the repository.
- [ ] Keep changes to the matching game source out of scope unless a documented, tested exception is necessary.

### Audio and threading

- [ ] Verify actual SDL/OpenAL audio callback/output on a supported Switch target; the CI ALSA check is inconclusive.
- [ ] Trace CD/XA/SPU audio data flow separately from the generated-tone probe.
- [ ] Confirm thread creation, synchronization, and rasterizer worker-pool behavior with the selected toolchain.
- [ ] Measure memory use and frame pacing on a physical device.

## Recommended order

1. Complete the source-level inventory of bootstrap, presentation, and input APIs.
2. Implement the smallest presenter/input adapters isolated from game logic.
3. Add focused host-side tests for adapter/state transitions.
4. Run CI build and NeXium smoke tests after each isolated change.
5. Attempt an upstream desktop baseline build with locally supplied, legally obtained game data before attempting the Switch integration.
6. Treat physical Switch, audio, sustained-session, and performance checks as separate acceptance gates.

## Evidence discipline

Mark a task complete only when the linked workflow, log, test output, or device observation directly verifies it. A successful compile or a passing emulator probe must not be presented as proof that the upstream game port runs on physical Switch hardware.


## RGB24 GLES2 probe: runtime evidence (2026-10-14)

- [Run 38647421497](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38647421497) passed after replacing the overly strict near-black letterbox heuristic with viewport-boundary and corner-marker checks.
- [Run 38649912686](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38649912686) passed the SDL2 build and NeXium runtime jobs, including the RGB24 texture-upload probe with an immediate GL upload-error checkpoint.
- [Run 38650056910](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38650056910) passed the same checks after draining stale GLES error state immediately before the RGB24 upload. The checkpoint therefore tests the upload operation rather than reporting an unrelated earlier GL error.
- The synthetic frame is 321×240 RGB24 with a tightly packed 963-byte row, bottom-up source storage, distinct corner markers, and a gradient. “Odd-stride” here means a row byte count not divisible by four; it is not padded row storage.
- This evidence covers the isolated probe under NeXium. It does not verify the upstream renderer integration, physical Switch, long-running frame pacing, or original-game assets.

## Next implementation boundary

The next step is to extract the GLES2 presentation resources and operations from `probes/rgb24_texture_smoke.c` into a reusable module that assumes an already-current GLES2 context. SDL window/context creation, synthetic test-frame generation, event handling, and buffer swapping should remain owned by the probe/caller. The module should own only its GL program, vertex buffer, and texture; expose explicit initialization, frame upload/draw, and destruction; validate frame/layout inputs; and propagate GL failures instead of silently presenting stale texture contents. Integrate it into the probe first, then rerun host tests and the NeXium screenshot checks before considering any upstream renderer change.
