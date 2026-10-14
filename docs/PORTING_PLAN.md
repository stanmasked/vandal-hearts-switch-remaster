# Porting Plan

## Current status

**Source audit complete; graphical framebuffer NRO builds in CI; interactive runtime input and graphics presentation are not yet verified on an emulator or physical Switch.**

The upstream PC port is a native C project with a portable hardware-interface layer, but it is designed for desktop Windows/Linux/macOS. See [Upstream Audit](UPSTREAM_AUDIT.md) for findings and [Build Notes](BUILDING.md) for the dependency inventory.

## Phase 1 — Establish a reproducible baseline

- [x] Review upstream README, architecture, build docs, platform glue, and license notices.
- [x] Record the exact upstream commit SHA used for the audit.
- [ ] Build and run the unmodified desktop PC port, if dependencies and locally supplied legal game data are available.
- [ ] Record exact toolchain versions, commands, logs, and known issues.

**Exit condition:** a documented desktop baseline, or a clear report of blockers.

## Phase 2 — Map portability boundaries

- [x] Inventory major dependencies and license boundaries.
- [ ] Inventory all OS-specific APIs in the bootstrap and related files.
- [ ] Trace the graphics presentation path and isolate it behind a small interface.
- [ ] Evaluate SDL2, graphics, audio, threading, filesystem, and memory APIs against the chosen Switch homebrew toolchain.
- [ ] Keep changes out of the byte-matching game source unless there is a documented, gated reason.

## Switch package availability findings

The official devkitPro package recipes provide a plausible path closer to the upstream desktop dependencies:

- [switch-sdl2 package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/SDL2/PKGBUILD) builds SDL2 for the Switch target and declares dependencies on `switch-mesa` and `libnx`.
- [switch-mesa package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/mesa/PKGBUILD) provides the Mesa graphics library for the Switch package set.
- [switch-openal-soft package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/openal-soft/PKGBUILD) builds OpenAL Soft and depends on `switch-sdl2`.

This establishes that package recipes exist. The [SDL2 probe CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38523937214) confirms `switch-sdl2` installs in the CI image and links into three NROs: a software-renderer/input probe, an OpenGL ES 2.0 context probe, and a CPU-framebuffer-to-GL-texture upload probe. None has been run on an emulator or console. The texture probe checks the intended transfer path at compile/link level only; it does not establish visual correctness or compatibility with the upstream desktop renderer. Next, run the probes on an emulator or console and test OpenAL independently before choosing the upstream port architecture.

## Phase 3 — Switch homebrew feasibility prototype

- [x] Confirm devkitPro/devkitA64/libnx are available in the CI container.
- [x] Build a minimal test application without game code or game data.
- [x] Implement a controller-driven tactical grid and basic unit movement rules.
- [x] Share cursor/selection/movement state logic between the libnx and SDL2 software-renderer prototypes, with host-side transition tests.
- [x] Implement and compile a software-rendered RGBA8888 framebuffer grid.
- [x] Build and package a separate SDL2 window/input/software-renderer probe in CI.
- [x] Build and package a separate SDL2 OpenGL ES 2.0 context probe in CI.
- [x] Build and package a CPU framebuffer upload-to-texture probe using SDL2/OpenGL ES.
- [ ] Verify the framebuffer and SDL2 probes in an emulator or on actual hardware.
- [ ] Measure frame pacing and memory use on actual hardware.
- [ ] Verify audio and thread support independently.

**Exit condition:** reproducible homebrew test app with input and framebuffer presentation on the intended test environment.

## Phase 4 — Port platform services

- [ ] Add a Switch-specific presentation backend or a verified supported renderer path.
- [ ] Adapt bootstrap, memory handling, filesystem paths, and save locations as needed.
- [ ] Adapt audio and threading only after proving the chosen libraries/toolchain support them.
- [ ] Keep the original desktop targets working.

## Phase 5 — Playable baseline

- [ ] Build a Switch-targeted binary with locally supplied, legally obtained game data.
- [ ] Verify startup, controller navigation, rendering, audio, save/load, and scene transitions.
- [ ] Track crashes, performance, memory use, and known limitations.
- [ ] Compare behavior against the desktop baseline.

## Phase 6 — HD improvements

Only after the baseline is playable:
- [ ] Identify resolution-dependent assumptions and performance bottlenecks.
- [ ] Preserve original art/gameplay as a reference mode.
- [ ] Add optional visual improvements incrementally.
- [ ] Test scaling, UI legibility, texture filtering, aspect ratio, and performance.

## Licensing and release readiness

- [ ] Review upstream LICENSE, NOTICE, and DISCLAIMER before copying code.
- [ ] Treat the upstream repository as mixed-rights: GPL-2.0 applies to specified original PC-port code/tooling, not automatically to decompiled game code or game-derived data.
- [ ] Do not commit disc images, game executables, BIOS/SDK data, extracted assets, or generated copyrighted content.
- [ ] Never claim Switch support until it has been built and tested on hardware.
