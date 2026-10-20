# MAP02 Stage296 — independently repeat real GUI CPAL/FileLogger observations

**Research-only stacked Draft / DO NOT MERGE.** Parent [Stage294 PR #367](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/367), immutable Stage294 head `335da2c666d57caa429a1a4408935dcd046cdf1a`. No original PS1 ROM, soundtrack or licensed assets; no production Switch audio changes; no upstream NeXium changes.

## Why run again

[Stage294 successful Actions #39504242167](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39504242167) verified real GUI FileLogger files for both hints. For 21ms, after first guest input no CPAL callback entry/return or nonzero virtual PCM occurred; prejoin `audoutPlayBuffer` was entered without return. For 22ms, 8/8 generated optical CRC pages and nonzero PCM passed, with 2,262 matched CPAL callbacks and **zero** error-callback increments and **zero** `cpal stream error:` FileLogger lines. Earlier real 22ms trials reported 36, then 169 error-callback increments, so the error counter varied across independent runs. FileLogger lines have never been shown to map 1:1 to those counters.

## New source-pinned cohort

Use five independent Ubuntu 24.04 GitHub Actions matrix jobs, each on a distinct GitHub runner:
- 21ms requested Pulse hint: replicas 1 and 2.
- 22ms requested Pulse hint: replicas 1, 2 and 3.

Every job reuses byte-identical **pinned NeXium Stage287 ELF** SHA-256 `c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`, **ROM-free generated NRO** SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`, the same Stage294 guest shell route and the same Stage294 independent real optical/PCM/CPAL/FileLogger auditor. FileLogger data root is explicitly pinned via `NEXIUM_DATA_ROOT` on each isolated guest runner. Raw GUI log is not uploaded; only a sanitized bounded FileLogger receipt and hashes are archived. Generated research 48k PCM, images, lifecycle CSV and their derived results are archived separately with unique replica artifact names.

The aggregator downloads all five per-replica artifacts and strictly requires all five distinct source/run/head/hint/replica receipts. It compares archived independently re-parsed guest markers, eight-page optical CRC outcome, virtual PCM hash/sample counts, monotonic CPAL lifecycle snapshots, whole-process FileLogger line counts and guest-window CPAL error counters. Synthetic falsification tests reject missing replicas, stale run IDs, swapped hints, mismatched optical/PCM/CPAL receipts and false successes.

**A change in error-callback count is an observation, not a cause of playback or failure.** The whole-process FileLogger uses wall-clock timestamps and the CPAL lifecycle guest window uses monotonic clock: line totals must not be equated to guest-window error callback deltas. Repeated runs are descriptive, **not** a reliability estimate or proof that 21ms is invariably silent or 22ms invariably works. The Pulse requested latency hint is not a measured hardware period. A state of `STREAM_PLAY_RETURNED_OK` is not proof that a stream remains alive. A finite pending `audoutPlayBuffer` return does not establish a permanent deadlock.

## Source and merge boundaries

The Stage296 PR contains only this workflow, docs, Python cohort auditor and generated-only tests. It builds on the Stage294 Draft and must not be merged into `main` or treated as a Switch hardware validation. Do not claim a CPAL/ALSA root cause, repaired production audio, PS1 soundtrack fidelity or live Nintendo Switch DAC output from this cohort.
