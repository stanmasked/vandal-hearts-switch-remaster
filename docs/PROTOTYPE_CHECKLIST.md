# Switch Feasibility Prototype Checklist

## Purpose and status

This checklist tracks the smallest useful Switch homebrew experiment before any game code or game data is ported.

**Status: initial framebuffer and SDL2 texture-upload presentation, visible before/after frame changes, and two-press Right-arrow movement are confirmed in NeXium for both paths. The main libnx prototype also passed A selection, B cancellation, a valid move, and rejection of out-of-range and enemy-tile moves. Graceful exit, audio output, and physical-console behavior remain unverified.**

The prototype uses devkitPro/devkitA64 and libnx. The latest main prototype passed toolchain checks, host-side rule tests, NRO header/segment validation, and artifact upload in [CI run 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405). The SDL2 software-renderer, OpenGL ES 2.0 context, and CPU framebuffer-to-texture probes passed package installation, compilation/linking, NRO validation, and artifact upload in [CI run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415). The software-renderer and GLES2-context probes are compile/package evidence; the CPU-framebuffer texture-upload probe also passed the NeXium initial-frame screenshot check in [run 38524564337](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524564337). It does not prove compatibility with the upstream desktop OpenGL path. The latest texture-probe archive digest is `sha256:85b154a316d66b7d51eb7aa0c1bb057d967cec3a18178b2a5b3ae998c4984131`; it is not a checksum of the extracted NRO.

## Scope boundary

The prototype must be independent of Vandal Hearts and must not require a disc image, original executable, BIOS/font data, extracted assets, or other proprietary game data. Do not copy upstream game code into this test.

## Automated rule tests

The movement rules and input-state transitions are shared by the libnx prototype and SDL2 software-renderer probe. `make test` checks Manhattan distance, board bounds, movement range, the blocked enemy tile, cursor clamping, hero selection, valid/invalid moves, and canceling selection. These tests passed in [CI run 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405). They validate state logic, not actual controller hardware or runtime graphics.

## Milestones and required evidence

### P0 — Record the environment

- [ ] Record host OS and version.
- [ ] Record devkitPro, devkitA64, libnx, and any selected graphics/input library versions.
- [x] Record the repository revision and exact build command in CI workflow history.
- [ ] Capture the complete build output and exit code as a durable evidence record.

**Pass condition:** another developer can recreate the environment description and run the same command. A version list alone is not a successful build.

### P1 — Build a minimal homebrew application

- [x] Build an NRO without game code or game data.
- [x] Confirm that CI produces the expected NRO artifact.
- [ ] Record the artifact's SHA-256 checksum and preserve compiler/linker output.

**Pass condition:** the build exits successfully and produces the expected artifact. This is a compile result only, not proof that it runs.

### P2 — Verify runtime and controller input

- [x] Launch the main framebuffer NRO and SDL2 texture-upload probe in NeXium (software Vulkan).
- [x] Capture 1280×720 screenshots and detect the expected hero-marker color in both probes.
- [ ] Launch the application on physical Switch hardware.
- [ ] Confirm the title and control hints are visible and correctly oriented.
- [x] Verify one Right-arrow input moves the cursor exactly one tile in the main libnx prototype via NeXium's keyboard-to-controller mapping ([CI run 38525585386](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38525585386)).
- [x] Verify two separate Right-arrow presses move the cursor exactly two tiles in the main libnx prototype via NeXium ([CI run 38577626136](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577626136)).
- [x] Verify two separate Right-arrow presses move the cursor exactly two tiles in the SDL2 texture probe via NeXium ([CI run 38577968731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731)).
- [ ] Verify D-pad edge clamping, physical-controller input, and all other controller actions.
- [x] Press A while the cursor is on the hero to select it and reveal the movement range in NeXium ([CI run 38578473844](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844)).
- [x] Move to an in-range empty tile and press A; verify the hero moves and selection clears in NeXium ([CI run 38578473844](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844)).
- [x] Try to move outside the movement range; verify the move is rejected and hero/selection are preserved in NeXium ([CI run 38579336397](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397)).
- [x] Try to move onto the enemy tile from a valid two-tile range; verify the move is rejected and hero/selection are preserved in NeXium ([CI run 38579336397](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397)).
- [x] Press B while selected; verify selection clears without moving the hero in NeXium ([CI run 38578473844](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844)).
- [ ] Press Plus; verify the app exits cleanly.
- [ ] Record environment, steps, result, and any logs.

For a manual run, download the `vandal-hearts-switch-prototype` artifact from a successful workflow run, extract the `.nro`, copy it to `sd:/switch/vandal-hearts-prototype.nro`, and launch it from the Homebrew Menu. Use a Switch homebrew-capable test environment you control; do not include game images or proprietary assets.

The current source draws a software-rendered 8×6 grid into a libnx RGBA8888 framebuffer and uses a generated 5×7 bitmap font for labels. The [selection/cancel/valid-move smoke test](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844) confirmed 3,660 movement-range pixels when selected, zero after cancellation, and the hero marker moved from its original tile to the two-tile destination. The expanded [invalid-move test](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397) confirmed the hero stays at `(3, 2)` after an out-of-range attempt, then moves to `(4, 3)` on a valid attempt and stays there when the adjacent enemy tile `(6, 3)` is targeted. The [evidence archive](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397/artifacts/11902895081) has SHA-256 `a205c1269aef424621a60747f22167c3cf429b3646cf064f78d17b944f3e2457`. Its latest artifact [11902636964](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578497998/artifacts/11902636964) has SHA-256 `b11f7b8bbe32c48416476ec66cad1c441aa5b6af9ae45c7bb9ececa78b83ff26`. The separate SDL2 texture probe uploads a CPU-generated RGBA frame to a GLES2 texture and presents it with a fullscreen quad. The NeXium graphics run detected the hero-marker color in both 1280×720 screenshots ([run 38524564337](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524564337)); the corrected libnx runtime check confirmed 3,163 changed pixels and a cursor move from `(1, 2)` to `(2, 2)` ([run 38577207363](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577207363), [evidence archive](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577207363/artifacts/11901710901), SHA-256 `48e06be83db950cb8bacb3547c68b1fc96e4ed0e012ea5fd0655c87a569b46b5`). The SDL2 texture check confirmed 2,466 changed pixels and the same one-cell Right-arrow movement ([run 38577215473](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577215473), [evidence archive](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577215473/artifacts/11900352598), SHA-256 `0ec3b4d9628dfea0da8dfc96aa850b752161e66d58aa702a0abfb33ed9e47cab`). A follow-up SDL2 test confirmed two separate Right-arrow presses moved the cursor from `(1, 2)` to `(3, 2)` with 2,614 changed pixels ([run 38577968731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731), [evidence archive](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731/artifacts/11900408330), SHA-256 `2dba37524313e1b44c98034f968f62763547f5c815bdfa942cd6c5aad9f03fcb`). An OpenAL Soft probe compiles/packages a generated-tone test, but audible output is not yet confirmed.

**Pass condition:** launch and input are observed in the named environment. Emulator results and physical-device results must be reported separately.

### P2b — Verify SDL2 package and link feasibility

- [x] Install the official `switch-sdl2` package and dependencies in CI.
- [x] Compile/link an SDL2 window, software-renderer, and controller/keyboard event probe.
- [x] Package the probe as an NRO and validate its header and segment bounds.
- [x] Compile/link and package a second probe requesting an OpenGL ES 2.0 context.
- [x] Compile/link and package a third probe uploading a CPU-rendered RGBA framebuffer into an OpenGL ES texture.
- [x] Run the CPU-framebuffer-to-GLES2-texture probe in NeXium and detect the expected marker.
- [x] Verify one Right-arrow movement in the SDL2 texture probe via `SDL_JOYBUTTONDOWN` on NeXium ([CI run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434)).
- [ ] Run the SDL2 software-renderer and bare GLES2-context probes in a runtime environment.
- [x] Build an SDL_GL/OpenGL ES context probe separately from the software renderer.
- [x] Run the GLES2 texture-upload probe and verify one joystick-driven Right move in NeXium; standalone context and software-renderer runtime remain unverified.

The software-renderer and OpenGL ES 2.0 builds and artifact uploads passed in [CI run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415). The CPU-framebuffer-to-texture NRO passed the NeXium frame and one-step joystick-input checks in [run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434). Repeated interaction and runtime behavior of the software-renderer and standalone context probes remain unverified.

**Pass condition:** the probe launches, presents repeated frames, and responds to controller input in a named runtime environment. A successful SDL2 link is not proof that the upstream OpenGL path works.

### P3 — Verify graphics presentation

- [x] Implement a generated framebuffer pattern/grid without loading game assets.
- [x] Compile and package the framebuffer implementation in CI.
- [x] Verify initial 1280×720 framebuffer presentation and hero-marker visibility in NeXium.
- [ ] Verify orientation and repeated frame updates over time, including after controller input.
- [ ] Record chosen API, pixel format, stride handling, and any scaling.
- [ ] Check that the app exits cleanly.

**Pass condition:** the test pattern is visibly presented and updated during a sustained run. A successful compile or a static screenshot alone does not prove stable frame presentation.

### P4 — Measure a baseline

- [ ] Record run duration and observed frame pacing.
- [ ] Record memory information if the selected environment exposes a reliable measurement.
- [ ] Repeat the run and note intermittent failures.
- [ ] State which measurements are instrumented and which are estimates.

**Pass condition:** results are repeatable and include test conditions. Do not claim performance targets until targets and measurement methods are defined.

### P5 — Probe optional services separately

Only after P1–P3 pass:

- [ ] Test filesystem access in an app-appropriate location using a generated non-proprietary file.
- [x] Build and package a generated-tone probe using OpenAL Soft.
- [ ] Confirm audible tone output in an emulator or on physical hardware.
- [ ] Test thread creation/synchronization only if the intended port requires it.
- [ ] Record API/library versions, result, and cleanup behavior for each probe.

**Pass condition:** each service has its own evidence. One successful service must not be treated as proof that other services work.

## Evidence record template

| Field | Value |
| --- | --- |
| Date/time | |
| Source revision | `5e49689c58e925fc0c9075034e231e44b275a91c` |
| Host OS | GitHub Actions runner/container (see workflow logs) |
| Toolchain and library versions | Toolchain verification passed; exact versions not yet recorded here |
| Target environment | NeXium emulator on Ubuntu 26.04 with Lavapipe software Vulkan; initial-frame screenshots checked |
| Exact command | Root Makefile build via CI workflow |
| Build exit code | 0 (workflow build step succeeded) |
| Artifact path and checksum | Artifact `nexium-runtime-evidence`; archive SHA-256: `b87166a30807f4df404234e05784b0a1c652b8701862ccf33a00a18e97244b16` |
| Runtime steps | Launch libnx NRO in NeXium; wait 30 seconds; capture a screenshot; inject one Right-arrow press; capture the second screenshot; compare cursor-border pixels |
| Observed result | Both screenshots were 1280×720; cursor yellow counts moved from (371, 0) to (0, 481), confirming one tile of Right-arrow movement; SDL2 input and audio remain unverified |
| Logs / screenshots location | [Main build 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405); [NeXium input check 38525585386](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38525585386); [input evidence artifact](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874464900/zip); [SDL2 graphics evidence](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524564337); [SDL2 builds 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415) |
| Known limitations | Main libnx selection, valid move, out-of-range rejection, and enemy-tile rejection verified in NeXium; graceful exit, audio output, long-session stability, and physical-device behavior remain unverified |

## SDL2 joystick runtime evidence

| Field | Value |
|---|---|
| Source revision | `24b8fb0d2c5804e6fb6825b8d452497de38b7e74` |
| Target environment | NeXium on Ubuntu 26.04 with Lavapipe software Vulkan |
| Artifact path and checksum | Artifact `sdl2-nexium-runtime-evidence`; archive SHA-256: `8207cc7d8076c941543ca6e5216e9df0ef02bd933f8fbbadd76697f9b49a635b` |
| Runtime steps | Launch SDL2 texture NRO; wait 30 seconds; capture frame; inject one Right press for 30 ms; capture second frame; scan all 48 grid cells for cursor outline |
| Observed result | Both screenshots were 1280×720; hero-marker pixels were 1,035 and 1,036; cursor moved from cell `(1, 2)` to `(2, 2)` with yellow-border counts 360 and 413 |
| Logs / screenshots location | [NeXium SDL2 runtime run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434); [evidence artifact](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11876567065/zip) |
| Known limitations | Two SDL2 Right-arrow presses verified; A/B interaction, long-session stability, audio, and physical Switch behavior remain unverified |

Do not commit proprietary game files or include them in CI artifacts. Use generated test data only.

## Decision gate

Do not begin porting the game renderer until the minimal application has demonstrated controller input and repeated framebuffer presentation in the intended environment. If a milestone fails, preserve the exact error and reduce the experiment to the smallest reproducible case.

A prototype result does not establish that the upstream PC port, its OpenGL/OpenAL dependencies, its memory/bootstrap code, or the complete game is compatible with Switch.

## References

- [Homebrew Guide — App development](https://switch.homebrew.guide/homebrew_dev/app_dev.html)
- [libnx framebuffer API](https://switchbrew.github.io/libnx/structFramebuffer.html)
- [Upstream PC port audit](UPSTREAM_AUDIT.md)
- [Build notes](BUILDING.md)
