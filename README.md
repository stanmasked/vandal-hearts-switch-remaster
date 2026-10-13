# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: planning / research.** Nintendo Switch compatibility has not been
> established. This repository does not currently contain a working Switch port.
> No build or on-device test is claimed.

## Goals

- Audit the upstream PC port, its architecture, dependencies, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [ ] Review upstream documentation and license.
2. [ ] Inventory dependencies, build system, renderer, audio, input, and file I/O.
3. [ ] Define a minimal Switch platform/build prototype.
4. [ ] Validate a playable baseline on supported hardware.
5. [ ] Plan and test optional visual improvements.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md),
and [legal notes](docs/LEGAL.md).

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
