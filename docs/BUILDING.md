# Build Notes

## Status

The minimal devkitPro/devkitA64/libnx homebrew build is verified in GitHub Actions: CI compiles the prototype and packages an `.nro` artifact. The current source includes a software-rendered 1280×720 RGBA framebuffer grid. This verifies compilation and packaging only; the application has not yet been verified on a Switch console or emulator, and it is not a port of the original game.

## Verified minimal Switch build

The repository's `Switch toolchain readiness` workflow runs toolchain checks and host-side rule tests, builds the ELF/NRO with the root `Makefile`, validates the packaged NRO, and uploads it as an Actions artifact. Run `make verify-nro` locally in a configured devkitPro environment to build the application and check its NRO header, declared size, and text/rodata/data segment bounds. A separate workflow installs `switch-sdl2`, builds an SDL2 window/software-renderer/controller probe, validates its NRO, and uploads it in [CI run 38523386492](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523386492). The graphical framebuffer source and tests passed in [CI run 38483880113](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38483880113). The latest main prototype build passed in [CI run 38523386542](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523386542); the SDL2 probe build passed in [CI run 38523386492](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523386492). Open the run and download the `vandal-hearts-switch-prototype` artifact.

The current program draws a generated 8×6 tactical grid directly into a libnx framebuffer, without fonts or game assets. D-pad moves the cursor; A selects the hero or attempts movement; B cancels selection; Plus exits. A successful CI build does not establish runtime behavior, controller usability, rendering performance, or compatibility with the original game. Do not describe this artifact as a playable port.

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

## First prototype

The minimal prototype now implements:
1. A homebrew application built with the selected toolchain.
2. Controller polling using libnx.
3. A generated software-rendered framebuffer grid in RGBA8888 format.
4. A simple cursor, hero marker, enemy marker, and movement-range visualization.

Next, run it in a named emulator or on physical hardware and verify orientation, repeated frame updates, controller behavior, and clean exit. Record the environment and evidence; do not infer runtime success from compilation.

Then create a dependency/API inventory for the upstream platform layer and port one interface at a time.

## Reproducibility checklist

- [ ] Upstream commit SHA recorded.
- [ ] Host OS and toolchain versions recorded.
- [ ] Desktop build result recorded (or blockers documented).
- [ ] Dependencies and licenses inventoried.
- [x] Minimal Switch input and framebuffer prototype built and packaged by CI.
- [ ] Framebuffer prototype run and tested on emulator or hardware.
- [ ] Switch graphics, audio, threading, and filesystem support verified.
- [ ] No proprietary game data included in the repository.
