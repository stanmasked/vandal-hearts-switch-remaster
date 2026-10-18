# Vandal Hearts Remake — Stage297: all audout calls versus actual queried-phase calls

The [Stage296 original-SD order reversal CI 39123296150](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39123296150)
has passed after fixing the legitimate phase8 partial-final-16-call
accounting in `4bf526b4`. It observed four independent current-run
SD sources in the order **0,8,8,0**.

The observation from real service queries alone was:

| Query measurements | First phase0 | First phase8 | Reversed phase8 | Reversed phase0 |
| --- | ---: | ---: | ---: | ---: |
| Actual query attempts | 122 | 121 | 120 | 120 |
| >=40ms audout calls ON queried attempts | 1 | 1 | 1 | 0 |
| Nonzero pre-submit service queue counts | 0 | 0 | 0 | 0 |

## Why this additional audit exists

Only one in every 16 audout attempts has an observed **service queue
count**, but every audout API call has a recorded latency bucket, and
every ≥40ms software call has an exact timestamp and attempt index.
To understand whether the observed subset is representative for
API call latency, Stage297 compares the queried-call rate against
the full **original guest SD source** within EACH capture.

The new `audit_nexium_phase_order_full_call_rates.py` rereads
the ORIGINAL current-run guest SD source for all four captures,
byte-binds every copied queue, clock, latency, slow, probe and
scene CSV, checks writer receipts, validates independent time
and attempt indexes, and recomputes the original service samples
for the selected actual phase.

It then computes with exact fractions, separately for software
calls ≥40ms and ≥50ms:

- Slow calls / **all actual audout attempts**;
- Slow calls / **actually queried attempts only**;
- The difference in those normalized rates for each capture;
- Between phase0 and phase8 in both forward and reversed order;
- The full-call versus queried-call contrast discrepancy.

It refuses dropped observations, missing slow-call source
accounting, fabricated service values and attempts to pass
an unverified Stage296 result. It DOES NOT impute the unknown
service queue counts on the other 15 phases.

The order is fixed, not randomized. Thus neither a phase
difference nor a full-sample discrepancy is evidence that one
query phase *caused* guest scheduling, playback, DAC starvation,
or audible defects on a real Nintendo Switch. Different sessions
have different clocks and are never considered frame-aligned.

The CI-produced `runtime-evidence/phase297-full-call-vs-queried.json`
is a source-bound software latency analysis, **not** a physical
audio quality report.
