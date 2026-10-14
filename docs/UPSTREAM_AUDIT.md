# Upstream PC Port Audit

**Audit date:** 2026-10-13  
**Upstream:** [HalmyLyseas/VandalHearts-PcPort](https://github.com/HalmyLyseas/VandalHearts-PcPort)  
**Upstream default branch:** `master`  
**Audited upstream commit:** [`14552fffa0e0b47e02b57592e274fc6e7a649923`](https://github.com/HalmyLyseas/VandalHearts-PcPort/commit/14552fffa0e0b47e02b57592e274fc6e7a649923)  
**Scope:** repository metadata, README, architecture/build documentation, build files, platform glue, renderer, and license notices. This is a source-level feasibility review, not a successful build or Switch test.

## Executive summary

The upstream project is a substantial native C port, not a thin SDL wrapper. It separates the byte-matching game decompilation from a PC platform layer that reimplements PlayStation hardware APIs. The PC layer has real portability work already, but it is explicitly designed for Windows, Linux, and macOS—not Nintendo Switch.

**Initial recommendation:** do not start by changing the decompiled game logic or attempting a whole-project cross-build. First isolate a small, independently testable presentation/platform seam, inventory every OS-specific assumption, and prove the toolchain/dependency path. A Switch port is plausible as an engineering experiment, but not yet established.

## Confirmed architecture

- The game source is organized as a matching decompilation; upstream documents byte-for-byte verification using `make check`.
- The native PC layer lives under `platform/pc/`, with portable C replacements for PS1 subsystem interfaces.
- Major backends include GPU/rasterization, GTE geometry, SPU/audio, CD-ROM/XA, MDEC video, and kernel/timing.
- The current desktop presentation path uses SDL2 for window/input, OpenGL on non-macOS desktops, and an SDL Metal renderer on macOS. Audio output uses OpenAL.
- The rasterizer includes a threaded high-resolution path using pthreads.
- The build supports Make and CMake, but the upstream Makefile is described as the reference implementation.

Sources: upstream [architecture](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/architecture.md), [building](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/building.md), and [PC CMake configuration](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/platform/pc/CMakeLists.txt).

## Build and dependency inventory

Required or normally enabled in the PC CMake configuration:

- A C compiler and CMake (CMake minimum version declared as 3.16).
- SDL2.
- OpenGL on non-Apple desktop targets.
- OpenAL.
- Python 3 for build-time data generators.
- Threads/pthreads.
- libwebp for optional HD background packs (enabled by default in CMake).
- FFmpeg/libav libraries (`avformat`, `avcodec`, `avutil`, `swscale`) for optional HD movie replacements (enabled by default in CMake).

The project can disable the optional HD-pack paths in its existing build system (`VH_WEBP=OFF`, `VH_HDVIDEO=OFF` in CMake), which is a useful first experiment for reducing dependencies. It does **not** prove the remaining stack is Switch-compatible.

## Main porting risks

### 1. Graphics presentation is desktop-specific

The current renderer presents the finished framebuffer through OpenGL calls on Windows/Linux (including legacy `glDrawPixels`) and through SDL's Metal renderer on macOS. A Switch target cannot be assumed to provide this desktop OpenGL path. The presentation layer will likely need a Switch-compatible backend or a supported SDL renderer path; this must be proven with a minimal framebuffer prototype before changing the game renderer.

**Concrete graphics API mismatch:** at the audited upstream revision, `platform/pc/src/pc_gpu_window.c` presents the software rasterizer output with `glPixelZoom`, `glRasterPos2f`, and `glDrawPixels` ([source lines 906–908](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/platform/pc/src/pc_gpu_window.c#L906-L908)). These are legacy desktop OpenGL APIs and are not part of OpenGL ES 2.0. Therefore, successfully creating a GLES2 context does not make the upstream presentation path compatible. The new texture-upload probe tests one possible replacement—uploading a CPU-generated RGBA frame to a GLES2 texture and drawing a fullscreen quad. NeXium runtime smoke now confirms its initial frame and one joystick-driven Right movement ([run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434)); physical-device validation and comparison against the upstream frame format, stride, orientation, and scaling behavior remain outstanding.

### 2. OS memory and executable assumptions

`platform/pc/src/pc_bootstrap.c` contains platform-specific branches for Windows APIs such as `VirtualAlloc`/`VirtualProtect`, POSIX `mmap`/`mprotect` and ELF inspection, and macOS Mach-O/dyld APIs. It also implements behavior needed to accommodate the original game's memory assumptions. A Switch implementation needs a careful audit of each behavior, not just replacement of the window code.

### 3. Audio and threading

OpenAL and pthreads are used by the desktop backend. Their availability, version, behavior, and packaging for the intended Switch homebrew toolchain must be checked independently. The high-resolution rasterizer's worker pool also needs performance and synchronization testing on device.

### 4. Build-time generation requires local source data

The build generates some files from a user-supplied original executable and a PsyQ `KROMDAT.BIN` or compatible BIOS font source. The upstream documents a raw 2352-byte-sector `.bin` disc image for runtime. These are not ordinary checked-in assets; the porting build must preserve the local-generation model and must not add proprietary files to this repository.

### 5. HD features should come later

The optional WebP background packs and FFmpeg/libav movie replacements add dependencies and more memory/performance variables. First target a baseline using the original disc data and native rendering/video paths; revisit HD replacements only after a playable baseline exists.

## Licensing and source boundaries

Upstream identifies the original PC-port code/tooling as **GPL-2.0**, but its `NOTICE` explicitly says that the GPL grant does **not** cover the decompiled Vandal Hearts game code or game-derived data. This is a mixed-rights repository, not a blanket license for every file.

Before copying files, preserve attribution and license notices, review the upstream `LICENSE`, `NOTICE`, and `DISCLAIMER`, and classify every copied or modified file. Do not assume the GPL grants rights to redistribute Konami/Sony material. Do not commit disc images, game executables, BIOS/SDK data, extracted assets, or generated copyrighted content.

## Recommended next steps

1. Record a specific upstream commit SHA and keep the first porting experiments reproducible.
2. Create a dependency/OS-API inventory for `platform/pc/src/` and its headers.
3. [x] Build and run a tiny Switch homebrew test that reads controller input and presents a test framebuffer without game data; main libnx and SDL2 texture probes pass a one-step Right-arrow test in NeXium.
4. [ ] Verify SDL2, graphics presentation, audio, and threading on a physical Switch; emulator evidence alone is not enough.
5. [ ] Prototype the PC port's presentation layer behind a small platform interface.
6. [ ] Build and test incrementally on hardware; log memory use, frame timing, input, audio, and save/file behavior.
7. [ ] Revisit HD improvements only after the unmodified baseline is playable.

## Follow-up runtime evidence (2026-10-14)

The initial no-game-data prototypes now have reproducible emulator evidence:

- Main libnx framebuffer: 1280×720 frame detected and one Right-arrow movement confirmed in [run 38525585386](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38525585386); [screenshots and logs](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874464900/zip).
- SDL2 texture-upload and joystick path: 1280×720 frame detected and one Right-arrow movement confirmed in [run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434); [screenshots and logs](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11876567065/zip).
- The SDL2 probe uses the devkitPro Switch joystick event path (`SDL_JoystickOpen` / `SDL_JOYBUTTONDOWN`), not only the desktop `SDL_GameController` event path.

These checks validate one graphics frame and one input transition in NeXium with software Vulkan. They do not establish physical Switch compatibility, sustained playability, audio output, the full SDL2 software-renderer path, or compatibility of the upstream desktop OpenGL renderer.

## What this audit does not establish

- It does not establish that the upstream project compiles for Switch.
- It does not establish that SDL2/OpenGL/OpenAL can be used unchanged on Switch.
- It does not establish a working build recipe or an on-device result.
- It does not grant rights to original game assets or proprietary Sony/Konami material.
