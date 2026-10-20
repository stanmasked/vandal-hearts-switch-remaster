# MAP02 Stage297 — source-pinned time bounds of real CPAL callbacks

**Research-only / DO NOT MERGE.** Child of [Stage296 Draft PR #372](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/372). This stage creates **no new ROM, NeXium binary, guest input, audio stream or licensed content**. It only rechecks original [Actions run #39506142824](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39506142824) real guest archives, pinned to Stage296 Git commit `3734b12fc2556481a702117175401d80b360db20`.

## Question

Does the 21ms CPAL callback stream already show no new callbacks *before* the first guest input, or does it become quiet only *after* the guest starts interacting with `audoutPlayBuffer`? The earlier Stage296 post-input deltas cannot answer that without inspecting the full original monotonic CSV.

## Method and audit gates

Download five **immutable, real, separate** Stage296 guest artifacts with the original run-id, not any current-run artifacts. Reuse Stage296 cohort fail-closed SHA/identity audit and independently run Stage288 CSV sanity validation for every original trace. Read `host-cpal-audioout-timeline.csv`, `guest-first-input-monotonic-ns.txt`, and `guest-final-observation-monotonic-ns.txt`. Recompute CPAL entries, returns, errors and guest AudioOut appends as positive per-snapshot counter differences and bound their first/last increments to their **two adjacent sample timestamps**. If an interval straddles guest input, classify it as `STRADDLES_INPUT`, **never** force it into before/after input. If there are no observed increments, label `NO_INCREMENT_SEEN_IN_CSV`, not `stream never executed` or `paused`.

Record the minimum objectively observed post-increment quiet *snapshot tail* in milliseconds. This measures the interval where no counter increment was observed across sampled checkpoints; it cannot prove a stream was deliberately dropped or paused, a thread deadlock, or the exact moment the final callback happened. State 3 `STREAM_PLAY_RETURNED_OK` proves a prior successful play call, not current running state.

The Stage297 code tests timing boundaries, a pre-input callback-only scenario, genuine post-input activity, an interval crossing the marker, counter values already positive before observation, invalid input clock bounds, impossible callback return counts and non-monotonic clock progression. All changes are isolated to one Python auditor, one test module, one workflow and this document. Raw third-party GUI logs are not republished.

## Inference boundary

Even if the 21ms trace shows no callback increments for its whole observed span, **that does not distinguish CPAL pause, device loss, scheduler behavior, failed initialization before sampling, or another audio backend state**. To establish the real root cause, future opt-in instrumented NeXium would need explicit monotonic markers for stream create/play/pause/drop and lower-level ALSA operations, without modifying game audio logic. No physical Nintendo Switch DAC behavior can be inferred from this Linux virtual Pulse test.
