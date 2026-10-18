# Vandal Hearts Remake — Stage 281: paired sensitivity within each temporal third

Stage280 [GitHub Actions 39081623437](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39081623437)
successfully reaudited eight original-SD-bound *archived* NeXium pairs
and partitioned **relative audio-service seconds 1–51** into exactly
three 17-second bins.

The observed switch-minus-idle differences in the **≥40 ms blocking
audout call rate per 1,000 calls** were:

| Relative guest-audio seconds | Observed rate difference (switch − idle) |
| --- | ---: |
| 1–17 | +0.370955 |
| 18–34 | +3.276119 |
| 35–51 | −1.154981 |

For ≥50 ms the respective differences were −1.001555, +0.604613,
and +0.202839 per 1,000 calls. These numbers are actual archived
software observations **without hardware or audible evidence**.
The different signs preclude treating the pooled +0.830 (≥40 ms)
as uniform over time.

## Stage281 analysis

`tools/analyze_nexium_steady_segment_sensitivity.py` receives both
reports **regenerated in the same CI workflow** from the previously
audited eight run archives. It recomputes all of Stage280 from Stage279
and rejects even a one-counter or one-run-ID discrepancy between that
recalculation and the supplied Stage280 report.

For each third and each 40/50 ms threshold, it computes:

- The actual **eight** individual within-pair rate differences,
  retaining numerator and denominator for each mode separately.
- The median difference and the min/max of eight **leave-one-pair-out**
  aggregate rates.
- Positive/negative/exact-tie pair directions reconciled with the
  independently validated per-segment `summarize` result.
- Fixed-seed, whole-*pair* resampling sensitivity (16,384 draws);
  audout calls within a run are **not independent bootstrap units**.

The report also reproduces the overall 51-second difference from the
unaltered full-window denominators. It neither averages per-segment
rates to manufacture a pooled result nor changes the eight raw archives.

Reproduce after the archive audit in the same CI job:

```sh
python3 tools/analyze_nexium_steady_segment_sensitivity.py \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
  --output verified-pairs/steady-state-three-17s-sensitivity.json
```

**Interpretation boundary:** fixed switch-before-idle order, nonrandomized
sessions and guest scheduler/host effects remain confounders. Leave-one-out
ranges and pair resamples are descriptive, *not* causal confidence
intervals. Neither NeXium software-call timing nor any synthetic
regression measures Switch DAC starvation, real speakers, music
authenticity or actual human-audible glitches. No Stage281 CI result
should be called successful before the new commit's run completes.
