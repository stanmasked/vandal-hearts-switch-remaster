# Vandal Hearts — Switch Homebrew Porting Research

An experimental, community-driven project to investigate whether the existing
[Vandal Hearts PC port](https://github.com/HalmyLyseas/VandalHearts-PcPort)
can be adapted for Nintendo Switch homebrew, with a longer-term goal of exploring
higher-resolution rendering and presentation improvements.

> **Status: early prototype.** CI builds a minimal Switch homebrew NRO with a software-rendered framebuffer grid. NeXium smoke tests confirm initial graphics output and one Right-arrow movement in both the main libnx prototype and the SDL2 joystick probe. Repeated interaction, audible audio, and physical Switch behavior remain unverified. This is not a working port of Vandal Hearts.

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
7. [x] Compile and package SDL2 software-renderer, OpenGL ES 2.0, and CPU-framebuffer texture-upload probes in CI.
8. [x] Compile and package an OpenAL Soft generated-tone probe in CI.
9. [x] Verify initial graphics output and one Right-arrow movement in the main libnx prototype through NeXium.
10. [x] Verify one Right-arrow movement in the SDL2 texture probe through NeXium's joystick API.
11. [ ] Verify physical-controller input, repeated interactive updates, audio, and a playable baseline on supported hardware.
12. [ ] Plan and test optional visual improvements.

Portable unit tests run with `make test` and are included in CI. They cover Manhattan distance, grid bounds, movement range, the blocked enemy tile, cursor clamping, selection, valid and invalid moves, and canceling selection. The shared state logic is used by both the libnx framebuffer prototype and the SDL2 software-renderer probe. The latest main build, host tests, NRO segment validation, and artifact upload passed in [CI run 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405).

The current prototype renders an 8×6 grid into a 1280×720 RGBA framebuffer using a generated 5×7 bitmap font; it requires no external fonts or game assets. D-pad moves the cursor; A selects the hero or attempts to move it; B cancels selection; Plus exits. Movement is limited to a Manhattan distance of two tiles, and the enemy tile is blocked. This is a mechanics/input experiment, not the original game's battle system. The NeXium smoke test confirms the initial frame and one D-pad movement in the main libnx prototype; it does not establish sustained playability.

The SDL2 feasibility workflow installs `switch-sdl2` and builds three probes: software rendering/input, OpenGL ES 2.0 context creation, and CPU framebuffer upload into an OpenGL ES texture. The latest builds, NRO validation, and artifact uploads passed in [CI run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415). The [NeXium graphics smoke run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524564337) launched both the main libnx framebuffer NRO and SDL2 texture-upload probe, detecting the expected hero marker in 1280×720 screenshots under software Vulkan. The [latest libnx input check](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38525585386) also verified one Right-arrow movement by comparing screenshots before and after input. The main libnx and SDL2 joystick paths each passed a single Right-arrow movement check in NeXium. Repeated interaction, audible audio, and physical-console behavior remain unverified; this does not prove that the upstream desktop OpenGL renderer is compatible. A separate [OpenAL Soft probe](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223445) builds and packages a generated-tone test, but audible output has not been verified.

See the [upstream audit](docs/UPSTREAM_AUDIT.md), [porting plan](docs/PORTING_PLAN.md),
[build notes](docs/BUILDING.md), [toolchain diagnostic instructions](docs/TOOLCHAIN_CHECK.md),
[prototype acceptance checklist](docs/PROTOTYPE_CHECKLIST.md), and
[legal notes](docs/LEGAL.md).

## Build artifact

The CI workflow creates an artifact named `vandal-hearts-switch-prototype`.
Download the latest main prototype from [CI run 38524223405](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223405) or use the [workflow runs page](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions).
The `vandal-hearts-switch-prototype` artifact for run 38524223405 is 53,315 bytes; GitHub reports archive SHA-256 `e79c0dff04aec3f2cf0d37c5427f4deb77106a94da96dd7af98cd4f026bde95b`. This digest identifies the GitHub artifact archive, not the extracted NRO file. The CI run checked the NRO magic, declared size, and segment bounds.

The separate [SDL2 probe run 38524223415](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415) uploaded three artifacts:
- [Software-renderer probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874333270/zip): archive size 2,796,343 bytes; archive SHA-256 `7c590339d0f132bfa0638f3d7474702be7f7b129478d854742e41c8df9b6ca7c`.
- [OpenGL ES 2.0 context probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874917294/zip): archive size 2,515,684 bytes; archive SHA-256 `3f28045dd96f14580ffae3db2f70328833021f291a093082f58b15f94e63d22e`.
- [CPU framebuffer-to-texture probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874832530/zip): archive size 2,517,588 bytes; archive SHA-256 `85b154a316d66b7d51eb7aa0c1bb057d967cec3a18178b2a5b3ae998c4984131`.
The [OpenAL Soft tone probe](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874329872/zip) from [CI run 38524223445](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223445) is 3,010,330 bytes; archive SHA-256 `4f9bc7b1116ffd73956436a72dabc1001bd773e7857d689fa042ee0ad53c973e`.
These digests identify GitHub artifact archives, not the extracted NRO files. The [libnx runtime evidence](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11874464900/zip) and [SDL2 runtime evidence](https://api.github.com/repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/11876567065/zip) contain 1280×720 before/after screenshots and logs showing one Right-arrow movement in each probe. Audio output and physical hardware remain unverified.

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
