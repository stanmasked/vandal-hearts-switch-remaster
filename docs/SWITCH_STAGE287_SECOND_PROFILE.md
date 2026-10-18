# Stage287 — NeXium 51-second audout slow-call localization

The [Stage286 independent eight-pair NeXium CI 39085333522](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085333522)
established that the temporal difference in the number of
40–<50 ms blocking audout API calls, rather than the total number
of audout attempts alone, dominates the previously reported
normalized temporal contrast. This does **not** measure audio
scheduler callbacks, DAC starvation, physical speaker output or
music authenticity.

## Per-second accounting, not new capture evidence

`tools/analyze_nexium_steady_second_profile.py` rederives and
checks **all Stage279–286 JSON reports** from the same previously
independently original-SD-audited eight historical NeXium source
archives in one CI job. It separately preserves guest-audio-service
seconds **1–51**, excluding cold-start second zero.

For each of 51 seconds, it calculates pooled idle and switching
attempts and slow-call counts (≥40 ms, ≥50 ms, and disjoint
40–<50 ms), the switching-minus-idle slow-call **rate** per 1,000
attempts, and the directions of the within-pair rate comparisons
for each of the same eight source workflows.

All raw per-second counters must sum exactly to the independent
51-second archived totals and to the three Stage280 17-second
partitions. At every second, for every paired mode, the
integer identity **≥40 ms = 40–<50 ms + ≥50 ms** holds.
The same identity for normalized differences is checked with
`Fraction` **before rounding**.

The report includes an explicitly post-hoc localization metric:
the **five** seconds having the largest *absolute pooled
per-second 40–<50 ms rate gaps*, and their fraction of the
sum of the 51 absolute individual-second gaps. This is an
**L1 concentration statistic**, NOT a share of the whole
51-second pooled rate (which has different denominators and
can cancel positive and negative second-level gaps).
It also reports positive/negative/zero seconds and the longest
consecutive run of positive observed per-second pooled rate
differences. These are descriptive, not inferential.

Reproduce after the Stage286 step in the verified eight-pair
workflow:

```sh
python3 tools/analyze_nexium_steady_second_profile.py \
 --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
 --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
 --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
 --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
 --verified-boundary-shifts verified-pairs/steady-state-fixed-left-boundary-shifts.json \
 --verified-boundary-pair-grid verified-pairs/steady-state-boundary-pair-grid.json \
 --verified-disjoint-bands verified-pairs/steady-state-disjoint-slow-call-bands.json \
 --verified-rate-exposure verified-pairs/steady-state-rate-exposure-decomposition.json \
 --output verified-pairs/steady-state-second-profile.json
```

Identifying an individual guest-audio-service second with unusual
audout timings is **not identifying a particular soundtrack
event or Switch OS scheduler stall**: no frame/event/DAC clock
alignment or independent order-randomized control exists.
No physical Switch listening test is implied.

## Independently verified Stage287 CI — 2026-10-18

All checks passed on code commit
[`9074a80e`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/9074a80e629f66f4c603bd6e7719ff4c92bbcbd3):

- [Eight-pair independent original-SD-bound archived source audit 39085780895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085780895).
- [Host SPU 39085780925](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085780925).
- [Native PCM Switch cross-compile 39085780872](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085780872).
- [Host C/Python tests and Switch toolchain 39085780878](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085780878).

The eight historical pairs produced the following **pooled-per-second
switching-minus-idle rate differences**, each evaluated over exactly
51 guest-audio-service seconds (seconds 1 through 51):

| Software API slow-call duration class | Positive seconds | Negative seconds | Exact ties | Longest positive sequence | Top-five absolute L1 share |
| --- | ---: | ---: | ---: | ---: | ---: |
| 40 ms ≤ time < 50 ms | **29** | **22** | 0 | **7** | **23.414%** |
| time ≥50 ms | 12 | 13 | 26 | 3 | 34.921% |
| time ≥40 ms | 29 | 22 | 0 | 8 | 24.498% |

For 40.. <50ms, the five **largest absolute** individual-second
rate gaps were:

| Relative guest-audio-service second | Absolute gap /1,000 attempts |
| ---: | ---: |
| 45 | 20.784128 |
| 15 | 20.649609 |
| 39 | 17.321917 |
| 1 | 17.057997 |
| 37 | 16.902557 |

The top-five **23.414%** value is a fraction of the sum of absolute
*individual-second rate gaps* (L1 mass, 395.984664 per 1,000 summed
across seconds), not a fraction of total 40–<50ms API calls and **not**
a decomposition of the full-duration pooled rate. The five seconds
were selected **after observing** the trace; their peaks are not
independent corroboration or a prespecified test statistic.

**Interpretation:** The sign varies over individual seconds despite
the positive archived window-level temporal contrast seen in
Stages 284–286. This reflects different aggregation, denominators
and temporal grouping, not a contradiction. The data neither align
host scheduler events to guest seconds nor randomize switching
versus idle capture order. No evidence establishes physical Switch
audio glitches, DAC underruns or scene-switch causation.
