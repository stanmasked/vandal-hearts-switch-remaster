# Switch backend porting notes

Status: research/design only. This document does not claim that the game runs on Switch.

## Current milestone

The first deliverable is a clean libnx homebrew build (`switch-test/`). It verifies the devkitPro toolchain and creates a minimal `.nro` with console output and controller input. It deliberately contains no upstream game code or game assets.

## Upstream baseline

The initial audit is pinned to upstream PC-port commit
[14552fffa0e0b47e02b57592e274fc6e7a649923](https://github.com/HalmyLyseas/VandalHearts-PcPort/tree/14552fffa0e0b47e02b57592e274fc6e7a649923).
The PC build is a native C engine port, but its platform layer is not a Switch backend.

## Data and build prerequisites

The pinned upstream CMake build validates a region-matching original PS-X executable and uses it to generate build-local includes; it also expects PsyQ `KROMDAT.BIN` or a BIOS containing the matching font data. Those files must be supplied locally by a lawful owner and must not be committed. Desktop CMake also requires SDL2, OpenGL on non-Apple systems, OpenAL, Python 3, and threads; optional WebP and FFmpeg support can be disabled, but that does not make the desktop backend Switch-compatible.

## Required platform work

1. **Build integration**
   - Keep a pinned upstream revision and make the build reproducible.
   - Add a Switch-specific build target instead of reusing desktop CMake defaults blindly.
   - Preserve the original data-generation and region validation requirements; do not check proprietary game files into this repository.

2. **Platform API audit**
   - Replace or isolate desktop-only assumptions in `platform/pc/`, especially virtual memory/protection and executable-image inspection in `pc_bootstrap.c`.
   - Audit file paths, timing, threads, input, audio device setup, and shutdown lifecycle against Horizon/libnx.
   - Avoid assuming that a desktop POSIX implementation is automatically compatible with Horizon.

3. **Graphics**
   - Identify every use of desktop OpenGL and its required features before selecting a Switch rendering path.
   - Evaluate an SDL2 GLES-capable route only after checking the renderer's GL calls and shader requirements. If unsupported calls are essential, add a compatibility layer or replace the renderer incrementally.
   - Keep the software rasterizer as a possible reference/fallback path while validating correctness and performance.

4. **Audio and media**
   - The desktop build links OpenAL; Switch needs a supported audio backend or a port of the engine's output path to libnx audio.
   - Start with native game audio paths. Optional WebP and FFmpeg HD replacements are separate work and should remain disabled until suitable Switch libraries and performance are proven.

5. **Runtime validation**
   - Validate boot, controller input, rendering, sound, save/load, suspend/resume, and long-session stability separately.
   - A successful compile is not evidence that the game boots or performs acceptably on hardware.

## Exit criteria

- [x] Smoke-test workflow produces and uploads a `.nro` artifact (console/input test; CI run `38440952887`).
- [x] Framebuffer color-bar test builds and uploads a separate `.nro` artifact (CI run `38440952887`).
- [x] Smoke-test source and build files are verified against the current devkitPro image.
- [x] Pinned upstream source fetch is verified in CI without copying game data into the repository.
- [ ] Upstream source is integrated at a pinned revision without proprietary assets.
- [ ] Switch-specific compile failures are resolved and documented.
- [ ] First boot is confirmed on a real Switch or a compatible test environment.
- [ ] Rendering/audio/input are validated before calling the project a playable port.
