# MAP02 v111 — native Unai writes versus sampled VRAM changes

Stacked Draft following v110 [PR #101](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/101).

## Why v111 matters

A v84 readback of 24 sampled VRAM positions can remain unchanged even if
instrumented native Unai 16-bit assignments occurred. Conversely, a
sampled change accompanied by no **instrumented** 16-bit store attempts
does not prove that no VRAM writes occurred: other GPU, DMA, assembly and
renderer paths are outside the instrumentation coverage. A same-value
store is a real assignment, not the absence of an assignment.

The v108/v109/v110 read-only audits already connect each strict Unai
four-record group to the corresponding GP0 command family and ordinal
position among four emulator VBlank callbacks. v111 now preserves the
*joint relationship* between readbacks and writes, rather than losing
it in separate independent per-class totals.

Each observed handler belongs to exactly one of four classes:

1. No sampled change, no instrumented stores.
2. No sampled change, with instrumented stores.
3. Sampled change, no instrumented stores.
4. Sampled change, with instrumented stores.

For every combination of VBlank interval, GP0 family and outcome, the
auditor conserves handler count, changed sample-point count, total
native 16-bit store attempts, same-value assignments and changed-value
assignments. Every partition is independently reconciled against v109
per-class/VBlank source totals and v110 pre-VBlank native-store
checkpoints. Additional four VBlank prefix counters track native
assignments associated with **unchanged sampled locations**.

## What the native tests establish

- A polygon command can report zero changed sample points but still
  have native pixel-store attempts, including both same-value and
  changed-value assignments.
- A changed sampled point with zero instrumented store assignments
  is kept as an explicit, *not causally explained* category.
- Two private traces can produce **identical v109 family histograms**
  and **identical v110 class-order/boundary snapshots** but different
  sample/store bindings. v111 distinguishes these traces.
- Malformed Unai four-event groups, VBlank splitting a handler, unsupported
  GPU commands, impossible samples or store counts are refused.
- The normal v85 fixture and preceding v108–v110 native summaries are
  revalidated on both GCC and Clang.

The pinned PCSX ReARMed GCC/Clang full synthetic-host workflow runs
the new audit on the existing **private** event journal and uploads only
sanitized class/interval/outcome counters under
`proof/public/v111-sample-store-divergence.json`. No raw command words,
pixels, addresses, original game resources, EXE or private JSONL leave
the private job.

## Strict limitations

The VBlank buckets refer to host observer append order and **not**
hardware GPU completion cycles or scanout timing. The 24 sampled
locations are not the entire VRAM; instrumented Unai C++ sites are not
all GPU hardware writes. This does not verify Vandal Hearts retail
MAP02, real hardware output or Switch HD rendering equivalence.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

`main` is unchanged.
