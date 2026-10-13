# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early porting experiments.** Nintendo Switch game compatibility has not been
> established, and this repository does not contain a working Vandal Hearts port. Three
> diagnostic homebrew `.nro` targets are being built in CI: console/input, framebuffer color bars,
> and an SD-card filesystem smoke test. They contain no game code or game data. No on-device test is claimed.

## Goals

- Audit the upstream PC port, its architecture, dependencies, and license.
- Identify platform-specific code and the smallest viable Switch homebrew path.
- Establish a reproducible build and test process before attempting visual changes.
- Investigate HD improvements only after the baseline game works reliably.

## Project status

1. [x] Review upstream documentation, license, and repository structure.
2. [x] Inventory major dependencies, build system, renderer, audio, input, and platform-specific memory handling.
3. [x] Add diagnostic Switch homebrew prototypes for console/input and framebuffer output; add an SD-card filesystem smoke test, pending CI/device verification.
4. [x] Add a host-tested PS1 main-RAM/scratchpad address-translation prototype, including tests for known sound-work and movie-ring-buffer offsets; it is not yet connected to the engine.
5. [x] Add a host-tested checked path-join helper for the future save-data adapter; it is not yet connected to game saves.
6. [ ] Design and implement a Switch-specific game backend; current diagnostics are not the game.
7. [ ] Validate a playable baseline on supported hardware.
8. [ ] Plan and test optional visual improvements.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [first Switch blocker audit results](docs/SWITCH_BLOCKER_AUDIT_RESULTS.md), [memory-model investigation](docs/SWITCH_MEMORY_MODEL_INVESTIGATION.md), [PS1 code-hit triage](docs/PSX_MEMORY_CODE_HITS.md), [PS1 memory call-site matrix](docs/PSX_MEMORY_CALLSITE_MATRIX.md), [memory boundary follow-up](docs/PSX_MEMORY_BOUNDARY_FOLLOWUP.md), [direct guest-pointer migration audit](docs/DIRECT_GUEST_POINTER_MIGRATION.md), [scratchpad separation audit](docs/SCRATCHPAD_SEPARATION_AUDIT.md), [sound-buffer lifetime audit](docs/SOUND_BUFFER_LIFETIME_AUDIT.md), [filesystem and save-data port audit](docs/FILESYSTEM_AND_SAVE_PORT_AUDIT.md), [save-data failure matrix](docs/SAVE_DATA_FAILURE_MATRIX.md), [save recovery design](docs/SAVE_RECOVERY_DESIGN.md), [libnx filesystem backend findings](docs/LIBNX_FILESYSTEM_BACKEND_NOTES.md), [save recovery design](docs/SAVE_RECOVERY_DESIGN.md), [memory translator prototype](docs/SWITCH_MEMORY_TRANSLATOR_PROTOTYPE.md), [PS1 memory scanner](scripts/audit_psx_memory_literals.py), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [Switch backend design](docs/SWITCH_BACKEND_DESIGN.md),
[pinned upstream workflow](docs/UPSTREAM_WORKFLOW.md), and [legal notes](docs/LEGAL.md).

The [GitHub Actions workflow history](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/switch-smoke-test.yml) shows current build status and downloadable artifacts. CI builds diagnostic NROs and uploads source-pattern audits; it also runs host-side memory translator tests and source audits. The filesystem smoke test is intended to verify libnx SD-card file I/O on-device, but no on-device result is claimed. The NROs are diagnostic only; this does not establish on-device game compatibility. The memory scan covers 156 source files: 3,325 main-RAM-shaped occurrences include 22 code-shaped and 3,303 comment/string matches; 4 scratchpad occurrences include 3 code-shaped and 1 comment/string match; there are no I/O-register-range hits; 3 zero/NULL-mirror occurrences include 1 code-shaped and 2 comment/string matches. Code-shaped hits still include inactive preprocessor branches and are not confirmed runtime accesses. The artifact is not a playable game.

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
