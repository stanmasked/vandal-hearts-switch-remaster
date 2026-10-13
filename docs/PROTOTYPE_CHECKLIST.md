# Switch Feasibility Prototype Checklist

## Purpose and status

This checklist tracks the smallest useful Switch homebrew experiment before any game code or game data is ported.

**Status: minimal NRO build verified in GitHub Actions; interactive runtime and controller behavior remain unverified.**

The prototype uses devkitPro/devkitA64 and libnx. CI run [38481552455](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38481552455) successfully built and uploaded an NRO artifact. That confirms the build and packaging pipeline, not that the app runs on a console or emulator.

## Scope boundary

The prototype must be independent of Vandal Hearts and must not require a disc image, original executable, BIOS/font data, extracted assets, or other proprietary game data. Do not copy upstream game code into this test.

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
- [ ] Show a visible running indicator.
- [ ] Verify D-pad cursor movement.
- [ ] Demonstrate A selecting a tile and B clearing the selection.
- [ ] Record environment, steps, result, and any logs.

The current source renders a generated ASCII tactical grid in the libnx console. Runtime behavior is not yet confirmed.

**Pass condition:** launch and input are observed in the named environment. Emulator results and physical-device results must be reported separately.

### P3 — Verify graphics presentation

- [ ] Present a generated test pattern (for example, color bars and a moving rectangle) without loading game assets.
- [ ] Verify correct orientation, expected dimensions, and repeated frame updates.
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
| Source revision | |
| Host OS | |
| Toolchain and library versions | |
| Target environment | Emulator name/version or physical-device description |
| Exact command | |
| Build exit code | |
| Artifact path and checksum | |
| Runtime steps | |
| Observed result | |
| Logs / screenshots location | |
| Known limitations | |

Do not commit proprietary game files or include them in CI artifacts. Use generated test data only.

## Decision gate

Do not begin porting the game renderer until the minimal application has demonstrated controller input and repeated framebuffer presentation in the intended environment. If a milestone fails, preserve the exact error and reduce the experiment to the smallest reproducible case.

A prototype result does not establish that the upstream PC port, its OpenGL/OpenAL dependencies, its memory/bootstrap code, or the complete game is compatible with Switch.

## References

- [Homebrew Guide — App development](https://switch.homebrew.guide/homebrew_dev/app_dev.html)
- [libnx framebuffer API](https://switchbrew.github.io/libnx/structFramebuffer.html)
- [Upstream PC port audit](UPSTREAM_AUDIT.md)
- [Build notes](BUILDING.md)
