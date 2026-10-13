# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early porting experiments.** Nintendo Switch game compatibility has not been
> established, and this repository does not contain a working Vandal Hearts port. Two
> diagnostic homebrew `.nro` files now compile in CI (console/input and framebuffer color bars);
> neither contains game code or game data. No on-device test is claimed.

## Goals

- Audit the upstream PC port, its architecture, dependencies, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [x] Review upstream documentation, license, and repository structure.
2. [x] Inventory major dependencies, build system, renderer, audio, input, and platform-specific memory handling.
3. [x] Build diagnostic Switch homebrew prototypes in CI (console/input and framebuffer color bars).
4. [ ] Design and implement a Switch-specific game backend; current diagnostics are not the game.
5. [ ] Validate a playable baseline on supported hardware.
6. [ ] Plan and test optional visual improvements.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [first Switch blocker audit results](docs/SWITCH_BLOCKER_AUDIT_RESULTS.md), [memory-model investigation](docs/SWITCH_MEMORY_MODEL_INVESTIGATION.md), [PS1 memory scanner](scripts/audit_psx_memory_literals.py), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [Switch backend design](docs/SWITCH_BACKEND_DESIGN.md),
[pinned upstream workflow](docs/UPSTREAM_WORKFLOW.md), and [legal notes](docs/LEGAL.md).

The latest successful [CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38443654383)
builds the diagnostic NROs and uploads the source-pattern audits as an [artifact](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38443654383/artifacts/11837901509). The memory scan covers 156 source files and found 3,321 main-RAM-shaped occurrences, 3 scratchpad occurrences, no I/O-register-range occurrences, and 2 zero/NULL-mirror occurrences. These include comments and inactive code; they are not confirmed runtime accesses. The artifact is not a playable game.

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
