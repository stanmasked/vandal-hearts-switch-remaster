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

## Verified Stage298 original-SD NeXium result — 18 October 2026

The [current-NRO independent NeXium run **39125903692**](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39125903692)
**completed successfully** on source commit
[`01a5fc00`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/01a5fc00e3fe01fdf8e02b086a57b53ac390d3d0).
The Stage296 order-reversal, Stage297 complete-call source
audit and new Stage298 exact partition all passed for the SAME
four source-original SD captures.

**These are new source sessions; do not substitute the counts
from the preceding Stage297 CI run 39124924827.**

| Guest software API duration >=40ms | Phase0 first | Phase8 first | Phase8 reversed | Phase0 reversed |
| --- | ---: | ---: | ---: | ---: |
| All original audout calls with duration >=40ms | **7** | **10** | **9** | **6** |
| >=40ms calls ON actually queried phase | 1 | 0 | 0 | 1 |
| >=40ms calls on other 15, UNQUERIED phases | **6** | **10** | **9** | **5** |
| >=50ms calls ON actually queried phase | 0 | 0 | 0 | 0 |
| >=50ms calls on other 15 phases | 0 | 1 | 1 | 0 |
| Actual service queue queries | 128 | 126 | 125 | 127 |
| Observed nonzero service queue results | 0 | 0 | 0 | 0 |

The two contrasts below are phase0-minus-phase8 rates **per 1,000
API attempts**, computed separately for different groups:

| Original-SD contrast >=40ms | First phase0/phase8 pair | Reversed phase0/phase8 pair |
| --- | ---: | ---: |
| Only actually queried calls | **+7.812500** | **+7.874016** |
| All software API calls | **−1.526613** | **−1.531173** |
| Other 15 unqueried phases' API durations | −2.149461 | −2.160084 |

This **sign reversal** between a systematic 1-in-16 sample and
the full set of original guest API call durations is independently
reproducible in the two within-run sequential pairs. However,
the sample groups and runs are neither randomly selected nor
causally balanced; the full-call contrast cannot prove anything
about audible output quality or which phase *caused* delays.

The actual SERVICE queue snapshots were made **only on the queried
phase**. No service queue count, DAC buffer, OS scheduling state
or speaker output was measured on the other 15 phases.
The other-phase numbers refer exclusively to independently recorded
**audout API call durations**, not queue observations.

Host C/Python plus Switch toolchain
[39125903653](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39125903653),
Host SPU [39125903661](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39125903661)
and native PCM [39125903657](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39125903657)
also completed successfully.
