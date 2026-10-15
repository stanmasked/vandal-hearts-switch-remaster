# Porting Plan

## Current status

**Source audit complete; initial framebuffer and SDL2 texture output, two-step Right-arrow movement in both paths, A/B/valid-move interaction, and rejection of out-of-range and enemy-tile moves in the main libnx prototype are confirmed in NeXium. Graceful exit, sustained interaction, audio output, and physical Switch behavior remain unverified.**

The upstream PC port is a native C project with a portable hardware-interface layer, but it is designed for desktop Windows/Linux/macOS. See [Upstream Audit](UPSTREAM_AUDIT.md) for findings and [Build Notes](BUILDING.md) for the dependency inventory.

## Current integration gate (2026-10-15)

The SDL2/GLES2 presenter feasibility work is now backed by the successful [runtime run 38693397077](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38693397077) and the post-documentation toolchain checks [38694347836](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694347836), [38694318016](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694318016), and [38694310888](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694310888).

**Source-tree check:** this repository still contains the Switch feasibility prototype and probes, not the upstream PC port's implementation files. In particular, `source/main.c` renders a generated tactical grid and is not the original game's entry point. The upstream renderer/bootstrap audit is based on a pinned, read-only inspection of `HalmyLyseas/VandalHearts-PcPort` at `14552fffa0e0b47e02b57592e274fc6e7a649923`; no upstream code has been imported or modified.

**Next integration gate:** establish a reproducible, pinned upstream-source checkout/build in CI and verify its required user-supplied game data and dependencies before connecting the presenter. Then make the smallest Switch-only presentation change at the audited final-frame boundary, preserving the desktop path. Do not treat the current probe as an integrated port. The upstream bootstrap's memory/executable assumptions, controller mapping, audio, and physical-console behavior remain separate open risks. No copyrighted game data is included in this repository.

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
- [x] Identify the upstream SDL_GameController input path versus the Switch SDL_Joystick event path; document the adapter requirement.
- [ ] Evaluate SDL2, graphics, audio, threading, filesystem, and memory APIs against the chosen Switch homebrew toolchain.
- [ ] Keep changes out of the byte-matching game source unless there is a documented, gated reason.

## Switch package availability findings

The official devkitPro package recipes provide a plausible path closer to the upstream desktop dependencies:

- [switch-sdl2 package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/SDL2/PKGBUILD) builds SDL2 for the Switch target and declares dependencies on `switch-mesa` and `libnx`.
- [switch-mesa package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/mesa/PKGBUILD) provides the Mesa graphics library for the Switch package set.
- [switch-openal-soft package recipe](https://github.com/devkitPro/pacman-packages/blob/master/switch/openal-soft/PKGBUILD) builds OpenAL Soft and depends on `switch-sdl2`.

This establishes that package recipes exist. The [SDL2 probe CI run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223415) confirms `switch-sdl2` installs in the CI image and links into three NROs: a software-renderer/input probe, an OpenGL ES 2.0 context probe, and a CPU-framebuffer-to-GL-texture upload probe. The texture-upload NRO has now run in NeXium and confirmed two Right-arrow movements ([run 38577968731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731)). The main libnx framebuffer NRO has also confirmed A selection, B cancellation, valid movement, out-of-range rejection, and enemy-tile rejection in NeXium ([run 38581542690](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38581542690)). These emulator results do not establish physical Switch compatibility or compatibility with the upstream desktop renderer. An [OpenAL Soft probe](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38524223445) installs `switch-openal-soft`, links an NRO, and packages a generated-tone test; audible output remains unverified. Next, validate graceful exit, audio, and physical-device behavior before choosing the upstream port architecture.

## Phase 3 — Switch homebrew feasibility prototype

- [x] Confirm devkitPro/devkitA64/libnx are available in the CI container.
- [x] Build a minimal test application without game code or game data.
- [x] Implement a controller-driven tactical grid and basic unit movement rules.
- [x] Share cursor/selection/movement state logic between the libnx and SDL2 software-renderer prototypes, with host-side transition tests.
- [x] Implement and compile a software-rendered RGBA8888 framebuffer grid.
- [x] Build and package a separate SDL2 window/input/software-renderer probe in CI.
- [x] Build and package a separate SDL2 OpenGL ES 2.0 context probe in CI.
- [x] Build and package a CPU framebuffer upload-to-texture probe using SDL2/OpenGL ES.
- [x] Launch the framebuffer NRO and SDL2 texture-upload probe in NeXium; verify the expected hero-marker color in 1280×720 screenshots.
- [x] Verify one Right-arrow movement in the main libnx prototype using NeXium's keyboard-to-controller mapping ([CI run 38525585386](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38525585386)).
- [x] Verify one Right-arrow movement in the SDL2 texture probe through NeXium's joystick API ([CI run 38526810434](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38526810434)).
- [x] Verify two separate Right-arrow presses in both libnx and SDL2 texture probes ([libnx run 38577626136](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577626136), [SDL2 run 38577968731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38577968731)).
- [x] Verify A selection, B cancellation, and a valid two-tile hero move in NeXium ([CI run 38578473844](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38578473844)).
- [x] Verify out-of-range and enemy-tile moves are rejected while preserving hero position and selection ([CI run 38579336397](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38579336397)).
- [ ] Verify sustained frame updates, audio output, and behavior on physical hardware.
- [ ] Measure frame pacing and memory use on actual hardware.
- [x] Build and package an OpenAL Soft generated-tone probe in CI.
- [ ] Verify audio output and thread support independently.

**Exit condition:** initial framebuffer presentation, repeated cursor movement in both libnx and SDL2 texture paths, and selection/valid/invalid movement in the libnx prototype are reproducible in NeXium. Graceful exit, sustained-session stability, audio, and physical Switch validation remain open.

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
