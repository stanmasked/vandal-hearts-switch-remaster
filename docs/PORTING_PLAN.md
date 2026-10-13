# Porting Plan

## Current status

**Research only.** The upstream PC port has not yet been audited in this repository,
and Switch compatibility is unverified. This plan is a sequence of investigation
and validation steps, not a claim that these steps are complete.

## Phase 1 — Establish a baseline

- Read the upstream README, architecture/build/cross-platform docs, contribution
  guidance, and license.
- Record the upstream commit or release being evaluated.
- Build and run the unmodified PC port on a supported desktop environment, if
  its dependencies and game-data requirements can be met legally.
- Record the exact build commands, toolchain versions, logs, and known issues.

**Exit condition:** a documented, reproducible desktop baseline, or a clear report
of what prevents it.

## Phase 2 — Map portability boundaries

Inventory:
- Build system and compiler assumptions.
- SDL or other third-party libraries and their target support.
- Graphics API, shaders, texture formats, and rendering assumptions.
- Audio, input/controller handling, filesystem paths, save data, and timing.
- Platform-specific APIs, threading, memory use, and external tools.

Separate portable game logic from platform-specific services where practical.
Do not replace major subsystems before the dependency map exists.

## Phase 3 — Switch homebrew feasibility prototype

- Verify current devkitPro/devkitA64/libnx documentation and the supported
  versions of required libraries.
- Determine whether the upstream renderer and SDL version can be supported,
  or whether a small platform abstraction is needed.
- Create a minimal build target only after the dependency and license review.
- Validate launch, input, file access, rendering, audio, and clean shutdown
  independently where possible.

**Exit condition:** a minimal homebrew build that launches on the intended test
environment, with reproducible instructions and logs.

## Phase 4 — Playable vertical slice

- Load one representative scene or battle using locally supplied legal game data.
- Test controller navigation, timing, audio, save/load, and scene transitions.
- Compare behavior against the desktop baseline.
- Track crashes, performance, and compatibility limitations.

## Phase 5 — HD improvements

Only after baseline compatibility:
- Identify resolution-dependent assumptions and rendering bottlenecks.
- Preserve original art and gameplay behavior as a reference mode.
- Make visual changes incremental and toggleable where feasible.
- Test scaling, UI legibility, texture filtering, aspect ratio, and performance.

## Phase 6 — Regression and release readiness

- Maintain a tested feature matrix and known-issues list.
- Document required tools and legal user-provided data.
- Verify licensing and redistribution rights for every shipped component.
- Never bundle proprietary game data or claim hardware compatibility without testing.

## Decision log

Record decisions here with date, evidence, alternatives considered, and follow-up
tasks. Unknowns should remain marked as unknown rather than assumed solved.
