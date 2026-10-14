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

The SDL2 feasibility workflow installs `switch-sdl2` and builds three probes: software rendering/input, OpenGL ES 2.0 context creation, and CPU framebuffer upload into an OpenGL ES texture. The latest builds, NRO validation, and artifact uploads passed in [CI run 38523937214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214). None has been run on an emulator or console; these probes do not prove that the upstream desktop OpenGL renderer is compatible.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named `vandal-hearts-switch-prototype`.
Download the latest main prototype from [CI run 38523936883](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523936883) or use the [workflow runs page](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions).
The `vandal-hearts-switch-prototype` artifact for run 38523936883 is 53,315 bytes; GitHub reports archive SHA-256 `02515abc9bc6bd850a5cc132e28b5018c9e3bacb457fc8e31f28c5a3a6c20ee1`. This digest identifies the GitHub artifact archive, not the extracted NRO file. The CI run checked the NRO magic, declared size, and segment bounds.

The separate [SDL2 probe run 38523937214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214) uploaded three artifacts:
- [Software-renderer probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874577442/zip): archive size 2,796,343 bytes; archive SHA-256 `1c99cf845b80ccda2fa41bb001aec592dde6d75725c1eb28f4e0dadafd73e06f`.
- [OpenGL ES 2.0 context probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874857230/zip): archive size 2,515,684 bytes; archive SHA-256 `57ab587f1ac7cf62f89e603294095c0588da31e4d6b4d7ebfd5e3187966331b6`.
- [CPU framebuffer-to-texture probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874567521/zip): archive size 2,517,588 bytes; archive SHA-256 `985bddb0751d0e9c93a439ed7469930295b97fc056b49072ea610839ce8c4f7a`.
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
