# Build Notes

## Status

No Switch build procedure has been verified. This document records upstream desktop requirements and the next investigations; it is not yet a recipe for producing a working Switch binary.

## Upstream build baseline

Upstream project: https://github.com/HalmyLyseas/VandalHearts-PcPort

The upstream repository separates the byte-matching decompilation from the native PC port. Its documented PC backend uses SDL2, OpenAL, OpenGL on Windows/Linux, and a Metal presentation path on macOS. It also uses Python 3 for build-time data generation and pthreads/Threads for its high-resolution rasterizer.

The upstream PC CMake file declares CMake 3.16 or newer and normally enables:
- SDL2
- OpenGL on non-Apple targets
- OpenAL
- Python 3
- Threads
- libwebp for HD background packs
- FFmpeg/libav (`avformat`, `avcodec`, `avutil`, `swscale`) for HD movie replacements

Optional HD dependencies can be disabled in the upstream CMake configuration with `-DVH_WEBP=OFF -DVH_HDVIDEO=OFF`. This only reduces the dependency set; it does not make the remaining stack Switch-compatible.

For upstream desktop build commands, follow its current [building guide](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/building.md). Do not assume its desktop commands cross-compile for Switch.

## Switch toolchain investigation

Before adding a Switch target:
- Confirm the current devkitPro/devkitA64/libnx toolchain and package support.
- Prove how the chosen runtime will create a window or framebuffer and present pixels.
- Check SDL2's target support and the actual renderer APIs available in the chosen Switch environment.
- Check audio support for the existing OpenAL-based backends.
- Check thread support and performance for the pthread worker pool.
- Audit OS-specific code in `platform/pc/src/pc_bootstrap.c`, including memory mapping/protection and executable-image inspection.
- Determine how locally generated files will be created without bundling copyrighted game data.

## First prototype (recommended)

Keep this separate from the game port:
1. Build a minimal homebrew application with the selected toolchain.
2. Read controller input.
3. Present a generated color-bar/test framebuffer.
4. Measure frame pacing and memory behavior on the actual target.
5. Add audio/threading probes only after the first prototype works.

Then create a dependency/API inventory for the upstream platform layer and port one interface at a time.

## Reproducibility checklist

- [ ] Upstream commit SHA recorded.
- [ ] Host OS and toolchain versions recorded.
- [ ] Desktop build result recorded (or blockers documented).
- [ ] Dependencies and licenses inventoried.
- [ ] Switch framebuffer/input prototype built and tested.
- [ ] Switch graphics, audio, threading, and filesystem support verified.
- [ ] No proprietary game data included in the repository.
