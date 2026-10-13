# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early prototype.** GitHub Actions has successfully built a minimal
> Switch homebrew NRO and the first interactive grid prototype. Runtime behavior
> is not yet verified in an emulator or on physical hardware. This is not a
> working port of Vandal Hearts.

## Goals

- Audit the upstream PC port, its architecture, dependencies, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [x] Review upstream documentation and license.
2. [x] Inventory dependencies, build system, renderer, audio, input, and file I/O.
3. [x] Build a minimal Switch homebrew prototype in CI.
4. [x] Implement a generated tactical grid with a hero, enemy marker, selection, and movement-range checks.
5. [ ] Verify controller input and runtime behavior in an emulator or on hardware.
6. [ ] Implement and validate a real framebuffer presentation test.
7. [ ] Validate a playable baseline on supported hardware.
8. [ ] Plan and test optional visual improvements.

Portable movement-rule unit tests run with `make test` and are included in CI; they cover Manhattan distance, grid bounds, movement range, and the blocked enemy tile. See the [CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38483716754).

The current console prototype provides a small 8×6 grid. D-pad moves the cursor;
A selects the hero or attempts to move it; B cancels selection; Plus exits.
Movement is limited to a Manhattan distance of two tiles, and the enemy tile is
blocked. This is a mechanics/input experiment, not the original game's battle system.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named vandal-hearts-switch-prototype.
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
