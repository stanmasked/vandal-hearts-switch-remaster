# Stage 283 — fixed left-shift sensitivity of the NeXium 17-second contrast

The Stage282 **middle (guest-audio seconds 18–34) minus late
(35–51)** contrast of switch-minus-idle ≥40 ms audout API-call rates
was **+4.431099 per 1,000 attempts**, from eight same-NRO
original-SD-audited archive pairs. It was positive in six of eight
per-pair temporal contrasts, and the eight leave-one-pair-out
aggregates remained positive. These are software API timings, not
DAC or audio output measurements.

A limitation is the *arbitrary boundary* at audio-service second 35.
Stage283 checks neighboring boundaries without adding any new data
or selecting a favorable one. It evaluates **every** one of five
predeclared left shifts, in ascending order:

| Shift | Earlier 17 seconds | Later 17 seconds |
| ---: | --- | --- |
| −4 | 14–30 | 31–47 |
| −3 | 15–31 | 32–48 |
| −2 | 16–32 | 33–49 |
| −1 | 17–33 | 34–50 |
| 0 | 18–34 | 35–51 |

A positive shift would extend beyond the last **verified** guest
audio second 51. No shorter run is padded, extrapolated or dropped.
Windows within a row do not overlap; windows across shifts **do**
overlap, so the five shifts are neither independent experiments nor
a set of unbiased new observations.

`tools/analyze_nexium_steady_boundary_shifts.py` recalculates the
entire prior Stage279→Stage282 chain and rejects any mismatch in the
Stage282 source report, NRO identity, run order or second counters.
For each fixed shift and threshold (≥40, ≥50 ms), it:

- Recalculates 17 actual per-second denominator/call-band totals
  in **both** idle and switching modes for each same-NRO pair.
- Computes the difference of the two *pooled* normalized
  switch-minus-idle rate differences without averaging rounded
  per-pair rates or silently replacing elapsed seconds.
- Preserves paired workflow IDs and reports eight run-specific
  temporal contrasts, sign counts and leave-one-pair-out extrema.
- Checks the zero-shift result *exactly* against Stage282 after
  rounding the direct unrounded contrast once to six decimals.
- Reports all five shifts, the min/max and count of signs
  instead of highlighting only the best shifted interval.

Run after generating all upstream reports from the same eight
audited historical source archives in one workflow execution:

```sh
python3 tools/analyze_nexium_steady_boundary_shifts.py \
 --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
 --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
 --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
 --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
 --output verified-pairs/steady-state-fixed-left-boundary-shifts.json
```

A separate CI step tests synthetic tampering, omission, reordering,
out-of-range seconds, and different denominators. The eight archived
source files remain unchanged, with earlier original virtual-SD checks
performed during the historical emulator workflows.

**Interpretation:** the experimental capture order was always
switching then idle; emulator scheduling, host contention,
and unknown actual audio hardware behavior remain. No temporal
shift analysis establishes music transition causality, audible
glitches, real DAC underruns, or original soundtrack fidelity.
Do not claim Stage283 succeeded until its own CI completes.
