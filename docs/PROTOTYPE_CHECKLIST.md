# Switch Feasibility Prototype Checklist

## Purpose and status

This checklist tracks the smallest useful Switch homebrew experiment before any game code or game data is ported.

**Status: graphical framebuffer prototype compiles and packages in CI; runtime presentation and controller behavior remain unverified.**

The prototype uses devkitPro/devkitA64 and libnx. The latest main prototype passed toolchain checks, host-side rule tests, NRO header/segment validation, and artifact upload in [CI run 38523936883](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523936883). The SDL2 software-renderer, OpenGL ES 2.0 context, and CPU framebuffer-to-texture probes passed package installation, compilation/linking, NRO validation, and artifact upload in [CI run 38523937214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214). These confirm build and packaging only, not runtime behavior. The texture-probe archive digest is `sha256:985bddb0751d0e9c93a439ed7469930295b97fc056b49072ea610839ce8c4f7a`; it is not a checksum of the extracted NRO.

## Scope boundary

The prototype must be independent of Vandal Hearts and must not require a disc image, original executable, BIOS/font data, extracted assets, or other proprietary game data. Do not copy upstream game code into this test.

## Automated rule tests

The movement rules and input-state transitions are shared by the libnx prototype and SDL2 software-renderer probe. `make test` checks Manhattan distance, board bounds, movement range, the blocked enemy tile, cursor clamping, hero selection, valid/invalid moves, and canceling selection. These tests passed in [CI run 38523936883](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523936883). They validate state logic, not actual controller hardware or runtime graphics.

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

- [ ] Launch the application in the explicitly named environment (emulator or physical console).
- [ ] Confirm the title and control hints are visible and correctly oriented.
- [ ] Verify D-pad moves the cursor and clamps it to the 8×6 board edges.
- [ ] Press A while the cursor is on the hero to select it and reveal the movement range.
- [ ] Move to an in-range empty tile and press A; verify the hero moves and selection clears.
- [ ] Try to move onto the enemy tile or outside the movement range; verify the move is rejected.
- [ ] Press B while selected; verify selection clears without moving the hero.
- [ ] Press Plus; verify the app exits cleanly.
- [ ] Record environment, steps, result, and any logs.

For a manual run, download the `vandal-hearts-switch-prototype` artifact from a successful workflow run, extract the `.nro`, copy it to `sd:/switch/vandal-hearts-prototype.nro`, and launch it from the Homebrew Menu. Use a Switch homebrew-capable test environment you control; do not include game images or proprietary assets.

The current source draws a software-rendered 8×6 grid into a libnx RGBA8888 framebuffer and uses a generated 5×7 bitmap font for labels. Runtime behavior is not yet confirmed.

**Pass condition:** launch and input are observed in the named environment. Emulator results and physical-device results must be reported separately.

### P2b — Verify SDL2 package and link feasibility

- [x] Install the official `switch-sdl2` package and dependencies in CI.
- [x] Compile/link an SDL2 window, software-renderer, and controller/keyboard event probe.
- [x] Package the probe as an NRO and validate its header and segment bounds.
- [x] Compile/link and package a second probe requesting an OpenGL ES 2.0 context.
- [x] Compile/link and package a third probe uploading a CPU-rendered RGBA framebuffer into an OpenGL ES texture.
- [ ] Run the SDL2 probes in an emulator or on physical hardware.
- [ ] Verify SDL2 event mapping and stable frame presentation at runtime.
- [ ] Test an SDL_GL/OpenGL context separately before attempting the upstream renderer.

The software-renderer and OpenGL ES 2.0 builds and artifact uploads passed in [CI run 38523937214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214). The generated NROs are about 6.7 MB and 6.1 MB before compression. This is compile/link evidence only.

**Pass condition:** the probe launches, presents repeated frames, and responds to controller input in a named runtime environment. A successful SDL2 link is not proof that the upstream OpenGL path works.

### P3 — Verify graphics presentation

- [x] Implement a generated framebuffer pattern/grid without loading game assets.
- [x] Compile and package the framebuffer implementation in CI.
- [ ] Verify correct orientation, expected dimensions, and repeated frame updates at runtime.
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
- [ ] Test audio output with a generated tone, if the chosen library supports it.
- [ ] Test thread creation/synchronization only if the intended port requires it.
- [ ] Record API/library versions, result, and cleanup behavior for each probe.

**Pass condition:** each service has its own evidence. One successful service must not be treated as proof that other services work.

## Evidence record template

| Field | Value |
| --- | --- |
| Date/time | |
| Source revision | `5e4b443da076b133f59e983346eac13ec0424141` |
| Host OS | GitHub Actions runner/container (see workflow logs) |
| Toolchain and library versions | Toolchain verification passed; exact versions not yet recorded here |
| Target environment | CI build only; runtime target not yet tested |
| Exact command | Root Makefile build via CI workflow |
| Build exit code | 0 (workflow build step succeeded) |
| Artifact path and checksum | Artifact `vandal-hearts-switch-prototype`; archive SHA-256: `02515abc9bc6bd850a5cc132e28b5018c9e3bacb457fc8e31f28c5a3a6c20ee1` |
| Runtime steps | Not yet run |
| Observed result | CI build and upload succeeded; no runtime claim |
| Logs / screenshots location | [Main build 38523589997](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523589997); [SDL2 probes 38523937214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214) |
| Known limitations | Compile verified only; emulator/device behavior unverified |

Do not commit proprietary game files or include them in CI artifacts. Use generated test data only.

## Decision gate

Do not begin porting the game renderer until the minimal application has demonstrated controller input and repeated framebuffer presentation in the intended environment. If a milestone fails, preserve the exact error and reduce the experiment to the smallest reproducible case.

A prototype result does not establish that the upstream PC port, its OpenGL/OpenAL dependencies, its memory/bootstrap code, or the complete game is compatible with Switch.

## References

- [Homebrew Guide — App development](https://switch.homebrew.guide/homebrew_dev/app_dev.html)
- [libnx framebuffer API](https://switchbrew.github.io/libnx/structFramebuffer.html)
- [Upstream PC port audit](UPSTREAM_AUDIT.md)
- [Build notes](BUILDING.md)
