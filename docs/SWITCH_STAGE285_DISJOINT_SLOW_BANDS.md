# Vandal Hearts Remake — Stage285: disjoint 40–<50ms vs >=50ms latency bands

Source: independently reaudited eight same-NRO NeXium runs, matched
guest-audio seconds 1–51 with cold-start second zero omitted.

[Successful Stage284 workflow 39084287880](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39084287880)
verified the **5 shifted boundaries × 8 leave-one-pair-out grid**:

| Threshold | Positive | Negative | Range per 1,000 API calls |
| --- | ---: | ---: | --- |
| ≥40 ms | 40/40 | 0/40 | +0.585548 … +8.058364 |
| ≥50 ms | 11/40 | 29/40 | −1.132053 … +0.687090 |

The dissimilar threshold patterns motivate a mathematically exact
split of the ge40 counters into non-overlapping:

- **40 ms ≤ duration < 50 ms** — calculated as audited
  `ge40 - ge50` integer counts.
- **duration ≥50 ms** — existing independently checked
  `ge50` counts, not duplicate slow-call observations.

The counts are **not new evidence** and no external audio is used.

## Implementation

`tools/analyze_nexium_steady_disjoint_bands.py` recomputes and
requires an exact match for every upstream Stage279–284 JSON witness
in the same GitHub Actions job. It then reconstructs both complete
17-second windows for each of five existing fixed boundary shifts.
For every window it calculates independent numerator/denominator
rates for idle and switching; it does the same after each of eight
whole-pair omissions from both modes/windows.

Unlike repeatedly subtracting rounded floats, it uses Python
`fractions.Fraction` to prove **exactly** for each mode's time drift,
and the final switch-minus-idle drift:

`contrast(>=40ms) = contrast(40.. <50ms) + contrast(>=50ms)`

This identity must hold before serializing results to six decimals.
A narrow six-decimal witness tolerance applies only when comparing
independently recomputed exact rational rates with Stage284's
historical rounded binary-float rates. The source integer counters
are never modified.

The output includes all 5 × 8 × 3 signed band values, separate idle
and switching temporal drift, and totals/positive/negative/tie counts
for each disjoint class. It does not predetermine or force any sign.
The existing ≥40 and ≥50 signs must reconcile with Stage284.

Run in CI only after regenerating upstream reports from the same
archived original-SD-bound inputs:

```sh
python3 tools/analyze_nexium_steady_disjoint_bands.py \
 --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
 --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
 --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
 --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
 --verified-boundary-shifts verified-pairs/steady-state-fixed-left-boundary-shifts.json \
 --verified-boundary-pair-grid verified-pairs/steady-state-boundary-pair-grid.json \
 --output verified-pairs/steady-state-disjoint-slow-call-bands.json
```

These are **software `audoutPlayBuffer` blocking durations**. They
cannot alone demonstrate music-transition causality, speaker output,
DAC underruns, actual hardware latency or a musical glitch. All
eight historical captures used switching before idle; temporal
positions and five overlapping shifts are not randomized independent
trials. Physical Switch listening is unmeasured.
