# Upstream PC renderer → Switch presenter integration plan

**Upstream source audited:** `HalmyLyseas/VandalHearts-PcPort` commit `14552fffa0e0b47e02b57592e274fc6e7a649923`.
**Switch presenter tested:** `source/switch_rgb24_presenter.c/.h` on branch `audit/switch-platform-boundaries`.
**Status:** integration design only; upstream PC source has not been modified or built as a Switch game.

## Narrowest presentation seam

In upstream `platform/pc/src/pc_gpu_window.c`, `PC_GpuPresent()` prepares the complete CPU-rendered frame before the final display operation. It converts native VRAM to RGB24, copies HD movie frames into the same buffer, applies movie subtitles and OSD/overlay drawing, then presents the result. This is the right first seam: keep the software rasterizer and post-processing intact and replace only the final platform presentation on the Switch build.

The scratch buffer contract observed at the audited revision is:

- RGB24 byte order (R, G, B), no alpha channel;
- tightly packed rows, `stride_bytes = width * 3`;
- bottom-up row order;
- borrowed/call-scoped storage, so the backend must finish uploading/copying before `PC_GpuPresent()` returns;
- dimensions can vary for movie frames, so texture storage must be resized safely.

The existing variable name `s_rgbaScratch` is misleading; the contents are RGB24.

## Source-level lifecycle and context audit

At the audited upstream revision, the following details were checked directly in `platform/pc/src/pc_gpu_window.c`:

- `PC_GpuInit()` creates the non-Apple window with `SDL_WINDOW_OPENGL | SDL_WINDOW_RESIZABLE`, then calls `SDL_GL_CreateContext()`. No explicit `SDL_GL_SetAttribute()` or `SDL_GL_MakeCurrent()` call appears in this file; the Switch-specific context profile therefore needs to be set before window creation, and the adapter should explicitly verify/current-bind the context before presenter initialisation.
- The final non-Apple draw is exactly the legacy immediate/pixel path: `glViewport()`, `glClear()`, `glPixelZoom()`, `glRasterPos2f()`, and `glDrawPixels()`, followed by `SDL_GL_SwapWindow()`. Only the drawing subsection should branch to GLES2; preserve the swap.
- This file has no `PC_GpuShutdown()`, `SDL_GL_DeleteContext()`, `SDL_DestroyRenderer()`, or general window teardown path at the audited revision. The only `SDL_DestroyWindow()` calls are error-unwind paths during initialisation. Before adding presenter resources, trace the application-wide shutdown/exit path and decide where a new GPU teardown hook belongs; do not assume a local shutdown function exists.
- The upstream scratch buffer is bottom-up for both VRAM conversion and the HD movie RGB24 copy. Subtitle and OSD routines mutate this same buffer before final presentation, so the Switch adapter must consume it only after those overlays have completed.

These are source-audit findings, not a compiled patch or runtime result.

## Application exit-path findings

A second pass followed the window/event path into the pinned upstream bootstrap and main loop:

- The game entry point in `src/core/main.c` is an infinite update loop; it has no normal return path.
- `PC_GpuPumpEvents()` calls `exit(0)` on `SDL_QUIT`. This is the ordinary window-close route, so a registered C `atexit` cleanup can cover that path, provided it is installed only after resources begin to exist and is idempotent.
- `pc_bootstrap.c` invokes `PC_GpuInit()` from a constructor before the game loop. A new public shutdown function is not currently called by the game loop and no GPU teardown API is declared in `pc_platform.h`.
- Recommended minimal lifecycle design for the Switch backend: implement an idempotent `PC_GpuShutdown()`; on successful/partial GLES setup register it once with `atexit`; keep the presenter destroy operation ahead of `SDL_GL_DeleteContext()` and `SDL_DestroyWindow()`. Make partial initialisation safe and clear pointers/flags as resources are released. If a later explicit application shutdown path is added, it may call the same function before process exit.
- Do not blindly call `SDL_Quit()` from this new function: SDL audio/game-controller and other subsystems are shared by the PC platform layer. Limit the initial teardown to presenter/context/window resources unless subsystem ownership is audited separately.

This is a source-based lifecycle recommendation. It has not yet been compiled or exercised in the upstream executable.

## Integration changes to make when the upstream source is available

1. **Compile-time backend selection.** Introduce a dedicated macro such as `VH_SWITCH_GLES2` in the PC platform layer. Keep the existing Apple Metal/SDL renderer and desktop OpenGL paths unchanged. Do not enable the Switch path by merely removing the desktop GL calls: `glDrawPixels`, `glPixelZoom`, and `glRasterPos2f` are not GLES2 APIs.
2. **Request an ES context before window creation.** In `PC_GpuInit()`, before `SDL_CreateWindow()`, set SDL GL attributes for an OpenGL ES 2.0 profile on the Switch build and use `SDL_WINDOW_OPENGL`. Create the context, make sure it is current, then initialise `VhSwitchRgb24Presenter`. Report context/presenter failures and unwind in reverse order.
3. **Replace only the final draw on Switch.** In the existing final-presentation block, construct `VhRgb24Frame { s_rgbaScratch, (size_t)w * 3u, w, h }`, validate it, upload it with `vh_switch_rgb24_presenter_upload()`, and draw it into the current drawable viewport with `vh_switch_rgb24_presenter_draw()`. Preserve the existing SDL window swap operation. Do not hold the scratch pointer after the call.
4. **Keep orientation and filtering single-sourced.** The upstream scratch buffer is bottom-up. The tested presenter/frame contract must decide the texture-coordinate orientation once; do not also flip the CPU rows. Preserve the centered aspect-ratio rectangle and nearest-neighbour intent. Explicitly verify RGB unpack alignment for odd-width movie frames.
5. **Lifecycle.** Initialise the presenter only after the GLES2 context is current. Destroy its texture, vertex buffer, and program while that same context is still current; only then destroy the context/window. Handle partial init and repeated init/shutdown without leaks or double destruction.
6. **Keep non-rendering assumptions separate.** A working presenter does not port bootstrap memory mapping, input mapping, audio, worker threads, or user-supplied disc-data access. Those remain independent acceptance gates.

## Test plan and acceptance gates

- [x] Unit tests for RGB24 frame validity, bottom-up row access, and aspect-preserving rectangle calculation exist in the Switch research repository.
- [x] Standalone GLES2 presenter build and NeXium checks cover RGB24 channel/orientation markers, an odd byte-count row, repeated frame updates, texture storage reuse, resize-and-restore, and rejected invalid metadata preserving the active frame dimensions. Latest evidence: [run 38694397097](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694397097), [runtime artifact 11954141491](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694397097/artifacts/11954141491).
- [ ] Compile the upstream desktop baseline with locally supplied, legally obtained data and record its exact upstream revision.
- [ ] Add the conditional GLES2 adapter without changing byte-matching game logic; ensure desktop build paths still compile.
- [ ] Feed a deterministic captured upstream frame through both desktop and Switch presenters; compare orientation, channel order, corner pixels, letterbox geometry, and nearest-neighbour output.
- [ ] Test variable-size movie frames and subtitle/OSD overlays after the adapter is connected.
- [ ] Run the integrated NRO in NeXium, then separately validate on physical Switch hardware.
- [ ] Measure sustained frame pacing and confirm orderly shutdown on target hardware.

## Current blocker

The current repository contains the Switch presenter and isolated probes, not the full upstream PC source tree. The integration seam is source-audited but not yet wired in. Do not report this as a working Vandal Hearts port until the integrated upstream build and runtime gates above pass.
