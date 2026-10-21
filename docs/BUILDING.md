# Build Notes

## Status

The minimal devkitPro/devkitA64/libnx homebrew build is verified in GitHub Actions: CI compiles the prototype and packages an `.nro` artifact. The current source includes a software-rendered 1280×720 RGBA framebuffer grid. NeXium smoke tests launched the main framebuffer NRO and SDL2 texture-upload probe under software Vulkan and detected the expected hero marker in 1280×720 screenshots ([initial graphics run 38524564337](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524564337)). The corrected checks confirmed visible before/after frame changes and a Right-arrow cursor movement in the main libnx prototype ([run 38577207363](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577207363)) and SDL2 texture probe ([run 38577215473](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577215473)). Follow-up tests confirmed two separate Right-arrow presses move the cursor two cells in the libnx prototype ([run 38577626136](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577626136)) and SDL2 texture probe ([run 38577968731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731)). A further [libnx interaction test](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844) confirmed A selection, B cancellation, and a valid move from `(1, 2)` to `(3, 2)` in NeXium. The expanded [run 38579336397](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397) also verified rejection of an out-of-range move and a move onto the enemy tile while preserving hero position and selection. Graceful exit, audio output, and physical Switch behavior remain unverified. This is not a port of the original game.

## Verified minimal Switch build

The repository's `Switch toolchain readiness` workflow runs toolchain checks and host-side tests for movement rules and input-state transitions, builds the ELF/NRO with the root `Makefile`, validates the packaged NRO, and uploads it as an Actions artifact. Run `make verify-nro` locally in a configured devkitPro environment to build the application and check its NRO header, declared size, and text/rodata/data segment bounds. A separate workflow installs `switch-sdl2`, builds and validates three probes (software renderer/input, OpenGL ES 2.0 context, and CPU framebuffer upload into a GL texture), and uploads all three NROs in [CI run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415). The graphical framebuffer source and tests passed in [CI run 38483880113](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38483880113). The [runtime evidence artifact](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874289721/zip) contains screenshots and logs for the initial-frame checks. The latest main prototype build passed in [CI run 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405); all three SDL2 probes passed in [CI run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415). Open the run and download the `vandal-hearts-switch-prototype` artifact. A separate OpenAL Soft workflow installs `switch-openal-soft`, compiles a generated-tone probe, validates the NRO, and uploads it in [CI run 38524223445](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223445); this does not verify audible output.

The current program draws a generated 8×6 tactical grid directly into a libnx framebuffer, without fonts or game assets. D-pad moves the cursor; A selects the hero or attempts movement; B cancels selection; Plus exits. A successful CI build does not establish runtime behavior, controller usability, rendering performance, or compatibility with the original game. Do not describe this artifact as a playable port.

## Upstream build baseline

Upstream project: https://github.com/HalmyLyseas/VandalHearts-PcPort

The upstream repository separates the byte-matching decompilation from the native PC port. Its documented PC backend uses SDL2, OpenAL, OpenGL on Windows/Linux, and a Metal presentation path on macOS. It also uses Python 3 for build-time data generation and pthreads/Threads for its high-resolution rasterizer.

Before attempting a local MAP02 PC-port build, run the read-only prerequisite checker and interpret its region fields carefully: [MAP02 PC-port preflight](MAP02_PC_PORT_PREFLIGHT.md). In particular, a boot/card ID that places a disc in the USA runtime family does not prove the image is the exact US retail release or satisfy the pinned data generator's US executable MD5 gate. Keep the full preflight report private because it contains local paths and hashes.

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

Next, verify graceful exit, audio output, long-session stability, and behavior on physical hardware. Record the environment and evidence; do not infer runtime success from compilation.

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
