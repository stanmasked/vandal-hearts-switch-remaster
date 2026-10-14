# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early prototype.** GitHub Actions has successfully built a minimal
> Switch homebrew NRO with a software-rendered framebuffer grid and interactive
> controls. Runtime behavior is not yet verified in an emulator or on physical
> hardware. This is not a working port of Vandal Hearts.

## Goals

- Audit the upstream PC port, its architecture, dependencies, build system, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [x] Review upstream documentation and license.
2. [x] Inventory dependencies, build system, renderer, audio, input, and file I/O.
3. [x] Build a minimal Switch homebrew prototype in CI.
4. [x] Implement a generated tactical grid with a hero, enemy marker, selection, and movement-range checks.
5. [x] Implement and compile a software-rendered framebuffer presentation path with generated bitmap labels.
6. [x] Validate the packaged NRO header and segment bounds in CI.
7. [ ] Verify controller input and repeated framebuffer presentation in an emulator or on hardware.
8. [ ] Validate a playable baseline on supported hardware.
9. [ ] Plan and test optional visual improvements.

Portable unit tests run with `make test` and are included in CI. They cover Manhattan distance, grid bounds, movement range, the blocked enemy tile, cursor clamping, selection, valid and invalid moves, and canceling selection. The shared state logic is used by both the libnx framebuffer prototype and the SDL2 software-renderer probe. The latest main build, host tests, NRO segment validation, and artifact upload passed in [CI run 38523844738](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523844738).

The current prototype renders an 8×6 grid into a 1280×720 RGBA framebuffer using a generated 5×7 bitmap font; it requires no external fonts or game assets. D-pad moves the cursor; A selects the hero or attempts to move it; B cancels selection; Plus exits. Movement is limited to a Manhattan distance of two tiles, and the enemy tile is blocked. This is a mechanics/input experiment, not the original game's battle system. A successful build does not prove that the framebuffer presents correctly at runtime.

The SDL2 feasibility workflow installs `switch-sdl2` and builds both a software-renderer/input probe and a separate OpenGL ES 2.0 context probe. The latest build, NRO validation, and artifact uploads passed in [CI run 38523844795](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523844795). Neither probe has been run on an emulator or console; a GLES2 context build does not prove that the upstream desktop OpenGL renderer is compatible.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named `vandal-hearts-switch-prototype`.
Download the latest main prototype from [CI run 38523844738](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523844738) or use the [workflow runs page](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions).
The `vandal-hearts-switch-prototype` artifact for run 38523844738 is 53,315 bytes; GitHub reports archive SHA-256 `86889244ff4d651ab2ec4cc09a59bd7514675dfc6edf07ca684f38e2a048f8b5`. This digest identifies the GitHub artifact archive, not the extracted NRO file. The CI run checked the NRO magic, declared size, and segment bounds.

The separate [SDL2 probe run 38523844795](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523844795) uploaded two artifacts:
- [Software-renderer probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11875177043/zip): archive size 2,796,343 bytes; archive SHA-256 `b34736727bcef49ee8e22327244c0b66389f003b4eff09950c0bb9b87282807b`.
- [OpenGL ES 2.0 probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11875491119/zip): archive size 2,515,684 bytes; archive SHA-256 `68e087af196709e90c09062d26a549bb336f953244da7e5161103961bc7cc33f`.
These digests identify GitHub artifact archives, not the extracted NRO files. All results prove compilation and packaging only; none confirms runtime behavior.

## Upstream

- [VandalHearts-PcPort](https://github.com/HalmyLyseas/VandalHearts-PcPort)

This project is independent and is not affiliated with or endorsed by the original
game's rights holders or the upstream project's maintainers.

## Game data

Do not commit disc images, proprietary game files, extracted assets, or other
copyrighted game data. Development should use legally obtained files supplied
locally by each user, where applicable and permitted by law.

## Contributing

At this stage, useful contributions include source-code analysis, dependency
inventory, documentation, build-system research, and reproducible test notes.
Do not describe Switch support as working until it has been built and tested.
