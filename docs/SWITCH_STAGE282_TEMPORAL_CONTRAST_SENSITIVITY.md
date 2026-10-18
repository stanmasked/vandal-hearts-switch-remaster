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

The **middle-minus-late contrast is +4.431100 per 1,000 calls**
as a difference between two *pooled* normalized rate differences.
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
