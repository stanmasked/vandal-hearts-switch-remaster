# MAP02 v67 — mutable GPU DMA RAM and complete emulator diagnostic build

## Why this is needed

The v66 PCSX ReARMed observer captured a single 2 MiB PS1 RAM address
space while GP0 GPU DMA2 linked-list submissions were being prepared.
In actual gameplay RAM is **mutable**. Retrospectively checking all
frames against a single final RAM snapshot can both reject genuine
observations and falsely associate a newer byte sequence with an
earlier GPU submission.

v67 keeps each pre-submit 2 MiB PS1 RAM image separate, immutable and
identified by its own SHA256 and monotonic submission frame index.

This is **not** GPU pixel verification and **not** a retail MAP02
capture; a CPU-side RAM snapshot taken just before GPU_dmaChain does not
prove that a GPU plugin actually consumed the same words.

## Pinned emulator source and diagnostic build

Public upstream: [notaz/pcsx_rearmed at
8b6c163575e6ce9a0537553e0d4ed4225315955e](https://github.com/notaz/pcsx_rearmed/tree/8b6c163575e6ce9a0537553e0d4ed4225315955e).

The new adapter script `tools/apply_map02_v67_pcsx_rearmed.py`
retains all strict pinned-version source anchors from v66 and swaps
in a bridge capable of emitting per-DMA RAM snapshots. Instrumented
points remain `psxHwWrite32` for GP1 MMIO writes and `psxDma2` for
linked-list GPU pre-submit RAM, with a disabled-by-default opt-in build.

The GCC+Clang CI attempts the actual **complete PCSX ReARMed frontend
binary** in the same pinned disposable checkout (SDL 1.2-based generic
frontend), *not merely compiling psxhw.c and psxdma.c*. The separate
C-hook smoke driver then runs the snapshot writer with synthetic-only
GPU data. Building an emulator binary is not proof of booting a game.

## Local capture

For a diagnostic PCSX build prepared from the pinned checkout:

```bash
python3 -m remaster.tools.apply_map02_v67_pcsx_rearmed /tmp/pcsx-rearmed-v67
make -C /tmp/pcsx-rearmed-v67 VH_MAP02_V66_PCSX_PROBE=1
mkdir -m 700 /private/pcsx-v67-frames
export VH_MAP02_V66_PCSX_LOG=/private/new-gpu-events.jsonl
export VH_MAP02_V67_SNAPSHOT_DIR=/private/pcsx-v67-frames
```

Every supported linked-list GPU submission creates
`frame-000000.ram`, `frame-000001.ram`, etc. The observer writes an
exclusive 0600 file using a private, owned (0700) directory. No GPU
data is automatically uploaded; all files must remain private.

The source bridge intentionally refuses unsupported OT addresses and
terminators, duplicate pointers, excessive nodes and oversized GP0
submissions, and appends an invalid event marker for parser rejection.
It does **not** promise exhaustive GPU-port capture. Non-DMA GP0 writes
and miscellaneous GP1 commands may occur in real games: v65/v67's
bounded grammar still rejects unsupported or interleaved cases.

Create a local hash manifest after capture:

```bash
python3 -m remaster.tools.audit_map02_v67_versioned_ram \
  --snapshot-dir /private/pcsx-v67-frames --frames 4 \
  --source-class user-supplied-unverified \
  --make-manifest /private/versioned-ram-manifest.json
```

Then correlate the **actual per-frame RAM versions** with all words
from the locally recorded GPU port log:

```bash
python3 -m remaster.tools.audit_map02_v67_versioned_ram \
  --snapshot-dir /private/pcsx-v67-frames \
  --manifest /private/versioned-ram-manifest.json \
  --probe /private/new-gpu-events.jsonl \
  --output /private/sanitized-v67-report.json
```

This strictly supports at most 64 frames of full 2 MiB snapshots,
with a separate expected hash for each, no symlinks for RAM inputs,
a bounded GP0 stream and unbroken event ordering. It preserves E1–E6
drawing state across DMA submissions and applies only explicitly
observed GP1(00)/(01) boundaries; other GP1 operations refuse.

The result includes counts, distinct RAM-version count and Boolean
proof gates, NOT RAM bytes, polygon coordinates, texture samples or
private paths. The manifest includes per-frame SHA256 values and
should remain private alongside the raw snapshots.

**Caution:** the 2 MiB raw snapshot contains entire PS1 RAM, which may
include copyrighted game data, personally identifying strings, or
unrelated information. Do NOT add genuine captures to the GitHub
repository or upload them to GitHub Actions. A self-computed SHA256 is
an integrity check, not independent hardware authenticity proof.

## Reproducible CI with synthetic data

The v67 sample deliberately changes FT4 vertex bytes in RAM before
frame 1 and again before frame 3. The emitter stores **three distinct
RAM versions across four frame submissions**, 80 GP0 words total,
one simulated GP1 full reset, and one FIFO-only reset. v67 must
compare each observed word with its *correct frame's* RAM image. It
explicitly checks that the legacy v65 single-final-snapshot contract
cannot validate the altered multi-frame stream.

Independent negative cases reject swapped snapshots, stale hashes,
modified GP0 payload words, nonmonotonic event ticks, unsupported
GP1 words, missing frames, bogus retail-provenance metadata,
symlinks and incomplete RAM files.

The CI inherits all v45–v66 original public-PC-port GPU raster/OT,
GTE/PRS, VHT1 trace, PS1 GP0 hardware-format and privacy regressions.
No proprietary retail resources or authentic MAP02 gameplay are used.

## Scope limits

- Source patch is prepared against a real pinned upstream; it is NOT
  installed in any independently verified user's running emulator.
- Complete diagnostic executable build (if CI passes) is **not**
  proof of a runtime emulator boot or accurate PS1 GPU raster output.
- Changing RAM snapshots and C hook observations alone do not
  independently certify GPU plugin consumption or retail provenance.
- `full_emulator_runtime_boot_verified=false`
- `gpu_plugin_gp0_fifo_consumption_verified=false`
- `retail_gp0_provenance_verified=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

Draft PR stacks on v66 and leaves `main` untouched.
