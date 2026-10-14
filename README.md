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

Portable movement-rule unit tests run with `make test` and are included in CI; they cover Manhattan distance, grid bounds, movement range, and the blocked enemy tile. The graphical framebuffer build and host-side tests passed in [CI run 38483880113](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38483880113). The latest bitmap-label build and NRO segment validation passed in [CI run 38522872471](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38522872471).

The current prototype renders an 8×6 grid into a 1280×720 RGBA framebuffer using a generated 5×7 bitmap font; it requires no external fonts or game assets. D-pad moves the cursor; A selects the hero or attempts to move it; B cancels selection; Plus exits. Movement is limited to a Manhattan distance of two tiles, and the enemy tile is blocked. This is a mechanics/input experiment, not the original game's battle system. A successful build does not prove that the framebuffer presents correctly at runtime.

A separate SDL2 feasibility probe also compiles and packages in [CI run 38523386492](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523386492). It uses an SDL2 window, software renderer, and controller/keyboard event handling. This confirms the Switch SDL2 package can be installed and linked in CI. A second [OpenGL ES 2.0 context probe](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523589761) also compiles and packages. Neither probe has been run on an emulator or console, and a GLES2 context build does not prove that the upstream desktop OpenGL renderer is compatible.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named `vandal-hearts-switch-prototype`.
Download the latest main prototype from [CI run 38523386542](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523386542) or use the [workflow runs page](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions).
The `vandal-hearts-switch-prototype` artifact for run 38523386542 is 52,944 bytes; GitHub reports archive SHA-256 `c38f23d4b24f037523d2a989ee52c6a2c8b113df82f1c2be7ae7a9e536ac80e2`. This digest identifies the GitHub artifact archive, not the extracted NRO file. The CI run checked the NRO magic, declared size, and segment bounds.

The separate [SDL2 probe run 38523589761](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523589761) uploaded two artifacts:
- `sdl2-switch-probe`: archive size 2,796,334 bytes; archive SHA-256 `1da8f08db8b5502e8a39ffbc6a68a9d45a47c1083e5b76ff3ab14fe486566b94`; NRO file size 6,737,976 bytes.
- `sdl2-gl-switch-probe`: archive size 2,515,684 bytes; archive SHA-256 `0aadb229f705cb5ef3f8a8709ee2f9fd9c28b30c0e12c2b61a89ab34f46e0c9c`; NRO file size 6,074,424 bytes.
The main prototype artifact for run 38523589997 has archive SHA-256 `875b0030f79f398b53e32d7456ce783423757cec8b93057ea2bf6bff760505f8`. These digests identify GitHub artifact archives, not the extracted NRO files. All results prove compilation and packaging only; none confirms runtime behavior.

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
