# Vandal Hearts Remake — Stage 282: time-position contrast robustness

Stage280's independently reaudited NeXium archival measurements
for eight complete, same-NRO idle/switch pairs found that the
*switch-minus-idle* rate of ≥40 ms blocking `audoutPlayBuffer`
calls per 1,000 calls varies across guest-audio service age:

| Included relative seconds | Switch minus idle rate |
| --- | ---: |
| 1–17 | +0.370955 |
| 18–34 | +3.276119 |
| 35–51 | −1.154981 |

Recomputing from the underlying integer segment totals, the
**middle-minus-late contrast is +4.431099 per 1,000 calls**.
Subtracting the two separately rounded six-decimal figures in the
table instead yields +4.431100, a one-unit last-decimal rounding
difference. The exact totals, not two pre-rounded rates, are the
accepted calculation.
It does not imply a particular difference in audibility, nor
identify music switching as the cause.

## Stage282

`tools/analyze_nexium_steady_temporal_contrasts.py` rederives
Stage281 from Stage279 and Stage280 and requires the Stage281
JSON to match exactly before any contrast is produced.

For each ≥40 ms / ≥50 ms threshold, it computes three earlier-minus-
later comparisons: early−middle, middle−late, and early−late.

Each comparison includes every one of the eight **matched source
workflow pairs**, pair-specific contrast signs, a median contrast,
leave-one-pair-out aggregate extremes, and a deterministic 16,384
resample exploratory percentile band.

Crucially, **each resampled workflow-pair ID is used in BOTH compared
time windows**. The tool never samples each temporal window
independently, since doing so would discard within-run dependence.
It also does not treat individual slow API calls as independent
experiments.

Run only after regenerating the three upstream reports from archived
inputs in the same GitHub Actions job:

```sh
python3 tools/analyze_nexium_steady_temporal_contrasts.py \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
  --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
  --output verified-pairs/steady-state-temporal-contrasts.json
```

The original eight guest virtual-SD files were independently checked
in their historical live CI runs. These later reports only re-open
the cryptographically bound archived copies, not the original runner's
SD directory. The host and emulator timing, nonrandomized fixed
switch-then-idle capture order, and scheduler confounders remain.
Resampling bands are **descriptive** and are not causal confidence
intervals or randomized significance tests. Nothing here verifies
physical Switch speakers, DAC underruns or original soundtrack
authenticity. Stage282 CI is a separate verification requirement.

## Accepted Stage282 independent CI (2026-10-18)

The corrected commit [`258b0de9`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/258b0de93b44cc20c10c998bcb598246746630fe)
passed [GitHub Actions 39082441354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39082441354),
including all eight original-SD-bound archive checks, Stage279,
Stage280, Stage281 exact recomputation, and Stage282's new matched-pair
time-contrast gate.

For **≥40 ms** audout service-call durations, the 18–34 second
minus 35–51 second difference was **+4.431099 calls per 1,000**,
with **6 of 8 pair-specific temporal differences positive** and a
leave-one-whole-pair-out aggregate range **+1.870709 to +6.930985**.
This is a descriptive time-dependent software observation under
fixed experiment ordering, not a randomized statistical inference.

The initial Stage282 CI at commit `f31b0f54` failed because it
compared the direct unrounded difference against the subtraction of
two separately rounded six-decimal Stage281 differences as if they
were bit-exact. The corrected source permits only the mathematically
bounded rounding discrepancy while still rederiving Stage281
exactly from the original verified input counts.

The [Stage282 Host SPU run 39082441225](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39082441225)
and [native PCM cross-build 39082441249](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39082441249)
also passed on the corrected commit. Physical Nintendo Switch
output, audible music quality, DAC underruns and soundtrack
authenticity remain **not measured**.
