# Stage368 — original audoutWait released-descriptor tuple, no extra service call

## Objective and original-source limit

The authentic older [NeXium #39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778)
returned `0xEA01` from its bounded tail wait and had software lease
counts `1414/1413/1`. The separate success [#39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727)
returned zero with `1438/1438/0`. Stage365 independently reaudited
both archives but **the older failed run has no Stage360 queue probe**.
Do not infer its queue size, physical playback or kernel subcall.

Stage357 recorded only the service `Result`. Stage368 adds a *separate*
bounded one-shot software witness capturing these values already
returned from the **same original** `audoutWaitPlayFinish` invocation:

- raw `Result` and the reported `released_count`;
- whether the returned descriptor pointer is non-null;
- whether that pointer equals the descriptor already submitted by the
  audio owner.

No pointer address is serialized. A returned pointer is only a
software descriptor observation; it does not establish DAC playback,
audible output or precise queue depth.

## Unchanged release behavior

The existing single `audoutWaitPlayFinish(..., 12000000)` call remains
unchanged; no extra service query, wait, clock query or memory allocation
occurs in this recording. Stage353 still makes the ownership decision
and Stage368 records only afterwards without changing its return.
If a wait fails, no lease is released; `audoutExit` still invalidates
the outstanding old-session descriptor. PCM, 48-kHz output and the
96-frame fade remain unchanged.

A new `VhAudioExitWaitDescriptor368` witness is reset at audio startup
and written by the single worker. A post-join-only CSV
`audio-exit-wait-descriptor-NNN.csv` uses an exclusive new file, exactly
eight numeric rows after `scope,value`, without rewriting the
original Stage313/347/351/357/360 evidence.

The CSV writer rejects inconsistent original Stage351 tail reasons,
Stage357 raw wait results, unobserved waits falsely classified as
success, a claimed successful release with a missing/mismatched
descriptor, and impossible absent/present pointer flags. A failed
service wait may still report an uninterpretable count or pointer;
the witness preserves it **without** using it to release ownership.

## Verification boundaries

[Stage368 workflow](../.github/workflows/stage368-original-wait-descriptor.yml)
runs GCC/Clang C11 optimized and UBSan synthetic controls plus Python
source integration checks that require exactly one original 12-ms wait,
a new exclusive post-join CSV and no extra audout/clock calls.

The new schema is **not proof of a real captured `0xEA01` run**.
Independent NeXium evidence from a newly built NRO must still establish
whether a real timed-out tail returns zero or nonzero descriptors and
how those outcomes differ between actual captures. Synthetic native
tests alone cannot explain the old timeout or verify physical speakers.
