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
3. Build a tiny Switch homebrew test that initializes the chosen runtime, reads controller input, and presents a test framebuffer—without any game data.
4. Verify the actual Switch support for SDL2, graphics presentation, audio, and threading in the chosen toolchain.
5. Only then prototype the PC port's presentation layer behind a small platform interface.
6. Build and test incrementally on hardware; log memory use, frame timing, input, audio, and save/file behavior.
7. Revisit HD improvements only after the unmodified baseline is playable.

## What this audit does not establish

- It does not establish that the upstream project compiles for Switch.
- It does not establish that SDL2/OpenGL/OpenAL can be used unchanged on Switch.
- It does not establish a working build recipe or an on-device result.
- It does not grant rights to original game assets or proprietary Sony/Konami material.
