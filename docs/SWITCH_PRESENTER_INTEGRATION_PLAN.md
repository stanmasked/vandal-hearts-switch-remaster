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

## Build-system integration findings

The pinned upstream `platform/pc/CMakeLists.txt` currently:

- unconditionally requires SDL2 and OpenAL, and requires desktop `OpenGL` whenever the host is not Apple;
- compiles `pc_gpu_window.c` into the common `vh_objs` object library;
- links the executable to `OpenGL::GL` on every non-Apple platform;
- links pthread-backed `Threads::Threads` for the threaded software rasterizer.

Therefore a Switch build cannot be enabled by changing only the C source. The CMake port needs a target-specific platform branch: omit the desktop OpenGL package/link on the Switch target, provide GLES2 headers/library and SDL2 from the Switch toolchain, and explicitly decide how OpenAL/audio and worker threads are supplied or gated. Avoid globally replacing desktop dependencies because the Windows/Linux builds must remain intact. These dependency decisions are not yet tested against the upstream build.

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

## Switch dependency matrix: current probes vs. upstream game

A comparison of this repository's actual Makefile/workflows against the pinned upstream CMake configuration separates dependencies already demonstrated in a Switch-target probe from dependencies still unproven for the game.

| Area | Current Switch research repository | Upstream PC port at audited revision | Integration decision / status |
|---|---|---|---|
| Toolchain / packaging | `devkitPro/devkita64`, `aarch64-none-elf-gcc`, `libnx`, `elf2nro`, `nacptool`; the base prototype links `-lnx` | Desktop-oriented CMake targets; no Switch target in the audited PC CMake file | The existing NRO pipeline is real and CI-validated, but it currently builds the research prototype, not upstream game objects. |
| SDL2 | Workflow builds SDL2 2.28.5 from source with the devkitPro Switch patch; both archive and patch are SHA-256 checked. Uses `sdl2-config` from `$DEVKITPRO/portlibs/switch/bin`. | `find_package(SDL2 REQUIRED)`; PC window/input code uses SDL2 | A usable Switch SDL2 build and probe path are demonstrated. Upstream source still needs a target-specific CMake/toolchain path. |
| Graphics API | GLES2 probes link `-lGLESv2`; a separate RGB24 texture presenter is built into an NRO and checked in NeXium | Non-Apple path requires and links desktop `OpenGL::GL`; final presentation uses `glDrawPixels`, `glPixelZoom`, and `glRasterPos2f` | Use a Switch-only GLES2 presenter branch; do not globally replace desktop OpenGL or try to compile the legacy draw calls as GLES2. |
| Audio | SDL2 is configured with `--enable-audio`; an SDL audio probe exists. OpenAL has a separate probe/workflow. | OpenAL is required by the PC CMake configuration | SDL audio configuration is not proof that the upstream game's audio code can use SDL instead of OpenAL. Audit OpenAL Soft's Switch availability/API compatibility and select a deliberate backend before enabling the game target. |
| Threads | SDL2 is configured with `--enable-pthreads`; toolchain host tests and sanitizer tests run separately | The software rasterizer links `Threads::Threads` | SDL2's pthread support does not automatically prove the upstream worker-thread code builds or behaves correctly. Check the actual thread API usage and target libraries in the port branch. |
| Window/context lifecycle | GLES2 context-creation and texture probes run in NeXium | Upstream window init has no explicit GL attribute selection or `SDL_GL_MakeCurrent` in the audited file; no ordinary GPU teardown path exists | Add ES 2.0 attributes before window creation, explicitly establish the current context, and make partial init/cleanup idempotent. |
| Assets / filesystem | Current prototype uses generated graphics and no original game assets | Original game bootstrap and data paths are outside the presenter | Disc-image extraction, file access, memory/layout assumptions and licensing are separate gates; none is solved by the presenter. |

### Build sequence recommended by this matrix

1. Preserve the existing desktop build unchanged and add a clearly named Switch target/platform option rather than altering global dependency rules.
2. Compile a minimal target object containing the upstream frame-preparation code plus the already-tested GLES2 presenter, with a tiny adapter seam. This is a compile test, not yet a playable game.
3. Introduce the upstream target's SDL2/toolchain settings and remove only the Switch target's desktop OpenGL dependency. Keep Windows/Linux links intact.
4. Resolve OpenAL and threading independently. A build should fail clearly if a required backend is absent; do not silently stub gameplay audio or thread behavior.
5. Only after the target compiles, add the upstream bootstrap and data-loading path, then run deterministic-frame comparison and emulator smoke tests.

### Confirmed evidence and limits

- The current `sdl2-probe.yml` workflow builds patched SDL2 2.28.5 with audio, joystick, pthread, timer and video options enabled; it builds software-renderer, GLES2 and RGB24-texture NRO probes. This demonstrates these isolated components can be built for the Switch toolchain.
- Toolchain readiness run [38750101998](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38750101998) completed successfully, including host rule tests, sanitizer-enabled host tests, NRO build/validation and artifact upload.
- Neither that workflow nor the SDL2 probe workflow builds the upstream PC-port CMake target. They do not yet verify upstream OpenAL linkage, its threaded rasterizer, its full bootstrap, or the original game running.

## Additional blocker: PC bootstrap is not a renderer-only port

A targeted source inspection of `platform/pc/src/pc_bootstrap.c` shows platform assumptions outside the presenter that need a separate compatibility design before the full PC-port executable can be built or launched on Switch:

- The non-Apple POSIX path attempts fixed-address `mmap(..., MAP_FIXED_NOREPLACE, ...)` reservations for PS1 RAM at `0x80000000` and scratchpad at `0x1f800000`. The code logs a warning and continues if either reservation fails, while noting that hardcoded pointers may then crash. These mappings must not be assumed available or harmless on Switch.
- The bootstrap has POSIX signal setup (`SIGUSR1`, `sigaction` for `SIGSEGV`/`SIGBUS`, `sigaltstack`) and write-fault/NULL-read recovery paths. The fault-context inspection explicitly uses x86 `ucontext_t` registers under `__i386__`/`__x86_64__`; those recovery mechanisms cannot be carried over as-is to AArch64/libnx.
- The same bootstrap also contains executable/rodata memory handling and constructor-driven startup. These are not equivalent to simply opening an SDL window on Switch and need to be isolated from the renderer patch.
- The bootstrap mounts a user-provided disc image before normal game startup. The current prototype uses generated graphics and does not exercise this path.

### Existing PC_PORT compatibility work already found

The initial direct-address spot check found that the upstream port already redirects several known PS1-memory uses under `PC_PORT`:

- `src/core/cd.c` maps the sound work buffers into a host-owned `sPcSoundWorkRam` allocation instead of literal `0x8014...` pointers.
- `src/core/cd.c` points the movie stream ring buffer at `gScratch3_80180210` under `PC_PORT`.
- `src/maps/unpack.c` uses a static 1 KB host scratchpad instead of `0x1f800000` under `PC_PORT`.

These are encouraging examples of the intended compatibility pattern, not proof that all absolute-address assumptions have been removed. The remaining audit should distinguish already-guarded core call sites from the bootstrap's fixed reservations and any unguarded references; avoid duplicating a memory abstraction that the upstream port already provides.

### Consequence

The earlier GLES2 presenter remains a useful, narrowly scoped component, but it is not sufficient to make the existing PC port runnable on Switch. Before the full game target is attempted, the port needs a documented AArch64/libnx strategy for PS1 address assumptions and fault-recovery behavior. Prefer replacing hardcoded PS1 RAM references with an explicit emulated-memory mapping/translation layer where feasible; any compatibility shim must be justified against the actual direct-address call sites and tested with game logic. Do not simply disable the fault handlers or ignore failed memory reservations and then label the result playable.

### Next source-level audit gate

- [ ] Inventory direct pointers to PS1 RAM/scratchpad and all call sites depending on them.
- [ ] Identify which rodata mutation and fault-recovery workarounds remain required under the AArch64 port build, rather than assuming the x86/Linux path applies.
- [ ] Propose a small platform abstraction and host-testable mapping contract before changing the bootstrap.
- [ ] Keep this bootstrap work independent from the completed standalone presenter tests.

