# MAP02 — Intel Mac offline, no-disc self-check

This is a **standalone, owner-local readiness command** for the source/GTE,
per-FT4 VRAM4, and native PC GPU packet tooling. It is deliberately useful
before the private PS1 drive or original capture is connected.

## Inputs

The command takes exactly one input file: a **public**, pinned
`pc_raster.c` from
`HalmyLyseas/VandalHearts-PcPort` commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`.
The verifier first checks the exact public raster Git blob; modified source,
symlinks or implausible file lengths are rejected.

The script refuses Linux and Apple Silicon. Its intended host is
`uname -s = Darwin`, `uname -m = x86_64`, Python 3.9 or newer, with
`clang` installed and available on PATH. Python tests and C compilation
use files already in the repository; they do not install dependencies,
access the network or open any real private MAP02 input.

## One owner-local command

From the repository checkout, where a separate public PC-port checkout
has already been placed locally:

```bash
python3 -m tools.map02_intel_mac_offline_selfcheck \
  /path/to/public/VandalHearts-PcPort/platform/pc/src/pc_raster.c
```

This runs the following **invented-data** checks on the actual Mac:

- 14 synthetic timeline source/GTE/VRAM tests.
- 25 synthetic combined PC-source/native GPU FT4 tests, including
  explicit distinct source/native frame clocks and original OT order.
- 3 **real subprocess CLI** cases: a successful private-format two-face
  file set, a deliberately incorrect cross-clock binding and a
  symlinked native VRAM file. Rejected inputs must not expose private
  paths, GPU colors, geometry, raw file names or captured binary data
  through stdout/stderr.
- 7 new **real subprocess CLI adversarial** tests (11 independently
  corrupted variants including GPU XY, UV, tpage, CLUT and E2 window,
  ambiguous packets, missing/changed VRAM, source/native material mismatch,
  path traversal and incorrect private-folder permissions). Their error
  output must never expose original paths, pixel values or raw payloads.
- Compilation and execution of the existing three-face C11 FT4
  source/CLUT/ordering-table fixture with local Clang.

The only stdout is a sanitized JSON readiness summary with counts,
boolean host/source status and explicit `false` values for original
PlayStation authenticity and Switch hardware proof. Failure uses a generic
diagnostic without caller-supplied file names or raw test data. Fixture
snapshots and test artifacts are temporary, invented data; no original
BIN/CUE, decoded MAP02, user-owned VRAM or private GPU packets are needed.

## GitHub validation

Dedicated GitHub Actions checks the **actual command** on macOS 15
Intel, Python 3.9 and Python 3.11; a separate Linux runner verifies
that a non-macOS host is rejected even with an arbitrary source path.
The acceptance marker is
`VH_MAP02_INTEL_OFFLINE_SELFCHECK_PASS` for each Python runtime.
Never treat merely imported modules or in-process tests as proof that
the user-facing CLI itself succeeds.

A passing CI is **not** a guarantee for Catalina 10.15.7 or the user's
specific Intel Mac installation; those require actual local execution.
Nor is this an original PS1 image authentication or a replacement for the
owner-private multi-stream GPU/VRAM capture. Keep Draft / unmerged.
