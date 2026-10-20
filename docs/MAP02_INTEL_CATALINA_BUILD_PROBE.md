# MAP02 — Intel Mac Catalina 10.15 Mach-O deployment probe

This optional **no-disc / no-original-asset** diagnostic extends the
offline self-check in Draft PR #348. The previous workflow ran 49 synthetic
tests and ten real subprocess CLI tests successfully on the GitHub-hosted
macOS **15 Intel x86_64** runner, using Python 3.9 and 3.11. That alone did
not establish compatibility with the owner's possible macOS Catalina host.

## Command

From a repository checkout on an **Intel Mac with Clang/Xcode Command Line
Tools installed**, and with an already downloaded **public** pinned
`pc_raster.c`:

```bash
python3 -m tools.map02_intel_mac_offline_selfcheck \
  /path/to/public/VandalHearts-PcPort/platform/pc/src/pc_raster.c \
  --deployment-target 10.15
```

The command does not require an original PS1 BIN/CUE, retail game binary,
original GPU captures, original artwork, ROM, private sector extracts or a
mounted external drive. It does not initiate network requests.

## What the optional flag does

- Requires actual `Darwin/x86_64`, Python 3.9 or newer, available Clang,
  an exact pinned **public** raster source Git blob and the same privacy
  guardrails as the prior self-check.
- Sets `MACOSX_DEPLOYMENT_TARGET=10.15` in the environment inherited by the
  existing **49 synthetic tests**, including ten actual source/native GPU
  command-line accept/reject probes. The target affects C compilations in
  those subprocesses, but their temporary executables are not preserved for
  independent load-command inspection.
- Independently compiles the existing three-face C11
  `test_map02_vram4_frame.c` with explicit
  `-arch x86_64 -mmacosx-version-min=10.15` and runs the compiled binary.
- Calls `lipo -archs` and `otool -l` on that **same compiled executable**
  before deleting it, requiring the exact x86_64 slice and an
  `LC_BUILD_VERSION minos 10.15` or legacy
  `LC_VERSION_MIN_MACOSX version 10.15` load command. It **fails closed**
  for a higher minimum such as 11.0, missing load command, missing tools
  or a different architecture.
- Returns only aggregate JSON, with
  `c11_macho_macos_minimum="10.15"`,
  `c11_macho_minimum_verified=true`,
  `synthetic_regressions_total=49` and separate
  `catalina_10_15_runtime_executed` status.

## What the evidence does NOT mean

A binary built against the SDK on macOS 15 with a Mach-O minimum of 10.15
has **not** thereby been run on Catalina. Targeting 10.15 also does not
independently prove that every possible runtime dynamic-library symbol,
Python installation, terminal toolchain or filesystem feature exists on the
owner's 10.15.7 system.

The GitHub CI intentionally requires
`catalina_10_15_runtime_executed=false` while using macOS 15.
**Only running the tool locally on actual macOS 10.15** can set that runtime
field true. Even then, the checks authenticate their invented fixtures,
not original retail gameplay or physical PlayStation/Switch hardware.

The public PC reference is checked by its exact Git blob.
No owner-owned game bytes, texture data, private paths or captured hardware
pixels are published. Keep all experimental work Draft and do not merge.
