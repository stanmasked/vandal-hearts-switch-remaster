# Vandal Hearts Remake — Stage286: what drives a normalized audout rate?

Stage285 [GitHub Actions 39084865077](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39084865077)
successfully revalidated eight original-SD-bound NeXium archival
switch/idle pairs and exactly partitioned slow blocking calls:
40.. <50ms was positive in **40/40** five-boundary × eight-deletion
temporal contrasts, whereas >=50ms was positive in **11/40**.

The temporal contrast is calculated from **slow call counts divided by
all audout attempts**, which can change because of the numerator,
the denominator, or both. Stage286 computes that accounting identity
instead of interpreting the raw normalized rate as a direct count
or hardware quality signal.

## Exact symmetric two-factor decomposition

For each mode (switching and idle), temporal pair of 17-second windows
and call duration class (>=40ms, 40..<50ms, >=50ms), let
`cE, aE` and `cL, aL` be early/late slow-call counts and all-call
attempts. The observed rate difference per 1,000 attempts is:

`R = 1000 * (cE/aE - cL/aL)`.

We compute **two exact symmetric components** as rational numbers:

```text
count_effect       = 500 * (cE - cL) * (aE + aL) / (aE * aL)
denominator_effect = 500 * (cE + cL) * (aL - aE) / (aE * aL)
R                  = count_effect + denominator_effect
```

This identity holds with no preferred baseline window. The
switch-minus-idle temporal contrast is calculated by subtracting
the corresponding idle components from switching components.
The combined >=40ms effects must also equal the sum of the
40..<50ms and >=50ms effects **exactly, before rounding**.

The new `tools/analyze_nexium_steady_rate_exposure.py` rebuilds
the full original Stage279–285 audit chain and demands exact
equality to the independently generated Stage285 source report.
It then records all original integer counts, attempts and components
for five boundary offsets and each of eight whole-pair deletions.
No source data, capture order or timing is modified.

Reproduce in the same CI job that verifies archived original-SD
evidence:

```sh
python3 tools/analyze_nexium_steady_rate_exposure.py \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
  --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
  --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
  --verified-boundary-shifts verified-pairs/steady-state-fixed-left-boundary-shifts.json \
  --verified-boundary-pair-grid verified-pairs/steady-state-boundary-pair-grid.json \
  --verified-disjoint-bands verified-pairs/steady-state-disjoint-slow-call-bands.json \
  --output verified-pairs/steady-state-rate-exposure-decomposition.json
```

Even a nonzero denominator component **does not prove** that host
load or an audio scene switch *caused* a change: the decomposition is
an exact arithmetic rearrangement, not a causal attribution.
All eight historical captures used switching before idle and
overlapping windows, so independence, randomization and device
inference remain unsupported. No Switch speakers, DAC starvation,
audible glitches or authentic game soundtrack are evaluated.

## Verified Stage286 CI — 2026-10-18

The Stage286 implementation commit
[`8f473c89`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/8f473c89b9170bfcd8e4c66f7363193ad655134e)
passed all required checks:

- [Eight-pair original-SD archive re-verification 39085333522](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085333522),
  including exact Stage279→286 reconciliation.
- [Host SPU 39085333526](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085333526).
- [Native PCM cross-compile 39085333518](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085333518).
- [Switch toolchain and host C/Python 39085333500](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39085333500).

Observed **5 shifts × 8 whole-pair omissions = 40 overlapping
source-cohort cells**, per disjoint duration band. All numbers
are **signed contributions to the temporal switch-minus-idle contrast
per 1,000 audout attempts**:

| Band | Positive count effects | Count effect min…max | Positive denominator effects | Denominator effect min…max |
| --- | ---: | ---: | ---: | ---: |
| 40 ms ≤ time < 50 ms | **40/40** | **+0.910639…+8.214194** | 38/40 | −0.025890…+0.196611 |
| time ≥50 ms | 9/40 | −1.142761…+0.685636 | 38/40 | −0.003539…+0.015514 |
| time ≥40 ms | 40/40 | +0.455266…+7.985936 | 38/40 | −0.028395…+0.211732 |

The count component is substantially larger than the denominator
component for the positive 40..<50ms contrast in all 40 archived
cells. This narrows the **arithmetic origin** of the rate difference
to more calls in that duration class, rather than exposure-only
denominator changes. It does not explain *why* those software
calls had that measured blocking duration.

Both decomposition terms are derived from the same historical
data and are correlated. Neither their magnitude nor 40/40 signs
measure statistical significance; the sessions were never
order-randomized. The tests still do not measure real console
audio, sound authenticity or DAC starvation.
