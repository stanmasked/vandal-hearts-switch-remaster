# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early prototype.** GitHub Actions has successfully built a minimal
> Switch homebrew NRO. The interactive tactical-grid input test is not yet
> verified in an emulator or on physical hardware. This is not a working port
> of Vandal Hearts.

## Goals

- Audit the upstream PC port, its architecture, dependencies, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [x] Review upstream documentation and license.
2. [x] Inventory dependencies, build system, renderer, audio, input, and file I/O.
3. [x] Build a minimal Switch homebrew prototype in CI.
4. [ ] Verify interactive controller input and runtime behavior in an emulator or on hardware.
5. [ ] Validate a playable baseline on supported hardware.
6. [ ] Plan and test optional visual improvements.

The current prototype renders a small tactical grid in the console, moves a cursor with
the D-pad, marks a tile with A, clears the mark with B, and exits with Plus. It uses no
original game code or proprietary game data.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named `vandal-hearts-switch-prototype`.
Download it from the [latest workflow runs](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions).
A successful CI build confirms compilation and packaging only; it does not confirm runtime behavior.

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
