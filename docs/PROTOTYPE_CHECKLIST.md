# Switch Feasibility Prototype Checklist

## Purpose and status

This checklist tracks the smallest useful Switch homebrew experiment before any game code or game data is ported.

**Status: graphical framebuffer prototype compiles and packages in CI; runtime presentation and controller behavior remain unverified.**

The prototype uses devkitPro/devkitA64 and libnx. The latest bitmap-label build passed toolchain checks, host-side rule tests, NRO header/segment validation, and artifact upload in [CI run 38522872471](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38522872471). This confirms the build and packaging pipeline, not that the app runs on a console or emulator. GitHub reports the uploaded artifact archive digest as `sha256:793a22d685dec40c791a81740687d69edf33c18f69148dae6a80a12fe5f52faa`; this is not a checksum of the extracted NRO.

## Scope boundary

The prototype must be independent of Vandal Hearts and must not require a disc image, original executable, BIOS/font data, extracted assets, or other proprietary game data. Do not copy upstream game code into this test.

## Automated rule tests

The movement-rule helpers are shared by the prototype and a host-side test executable. `make test` checks Manhattan distance, board bounds, valid movement range, and the blocked enemy tile. These tests passed as part of [CI run 38483880113](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38483880113). They validate the extracted rule functions, not controller behavior or runtime graphics.

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
| Source revision | `c4b98e4af743daea4b2d43d8152c84b667eeabc2` |
| Host OS | GitHub Actions runner/container (see workflow logs) |
| Toolchain and library versions | Toolchain verification passed; exact versions not yet recorded here |
| Target environment | CI build only; runtime target not yet tested |
| Exact command | Root Makefile build via CI workflow |
| Build exit code | 0 (workflow build step succeeded) |
| Artifact path and checksum | Artifact `vandal-hearts-switch-prototype`; archive SHA-256: `793a22d685dec40c791a81740687d69edf33c18f69148dae6a80a12fe5f52faa` |
| Runtime steps | Not yet run |
| Observed result | CI build and upload succeeded; no runtime claim |
| Logs / screenshots location | [CI run 38522872471](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38522872471) |
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
