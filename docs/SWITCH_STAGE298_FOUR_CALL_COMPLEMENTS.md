# Vandal Hearts Remake — Stage298: actually queried phase vs the other 15 attempt classes

This is a STRICT extension of the [Stage297 exact complete-call audit](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39124924827).
It MUST NOT run successfully until the new current-run original guest SD
source report `phase297-full-call-vs-queried.json` has been completely
recomputed and matched.

For each of the four sessions in capture order 0,8,8,0, there are
two disjoint sets of *software audio API attempts*:

- The actually queried SERVICE phase: attempts 1+16k for phase0
  or 9+16k for phase8, with measured pre-submit service queue
  counts on those exact attempts.
- All the other 15 attempt-index phases: complete software
  call-duration observations, but **NO queue service readings**.

All ≥40ms and ≥50ms software call durations are recorded in their
own original slow-call source independent of whether a service
queue count was queried. Stage298 calculates:

1. Counts and denominators for the actually queried phase, the
   other 15 phases, and the entire source run, using exact
   integer count conservation and Python `Fraction`.
2. The actual queried-phase latency rate minus the other-phase
   latency rate, and the exact weighted all-call rate identity.
3. Phase0-minus-phase8 differences for the first and reversed
   sequence of sessions, separately for queried, other-phase
   and full software call-duration data.
4. For each capture, entirely recalculates Stage297 using
   independent original guest SD files for queue, clock, latency,
   exact slow calls, probe samples and scene events.

The output is `runtime-evidence/phase298-query-complement.json`;
no source PCM, SPU, native audout hot path, build artifact or guest
audio-query frequency is modified.

This is **descriptive source-bound software API latency analysis**,
not a statistical randomized estimate, NeXium host scheduler trace,
physical Nintendo Switch DAC queue capture, audibly verified gameplay
or proof that changing the music/phase caused a slowdown.

The service queue count remains **UNMEASURED** on the other
15 classes and must NEVER be fabricated or inferred.
