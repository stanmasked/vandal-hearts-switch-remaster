# Vandal Hearts Remake — Stage 278: Eight-pair audio-call variability

**Accepted:** [GitHub Actions 39080141701](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39080141701) — independent eight-run archive re-verification plus a repeatable whole-pair variability analysis.

**Only guest NeXium software events were measured. HARDWARE NOT TESTED. Speaker underruns, user-audible effects and music-switch causality are not established.**

## New evidence

The eighth completed and original-SD-audited paired workflow is
[39079372486](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39079372486).
The full NeXium guest original-SD clock, scene, `audout` slow-call
histogram, exact nanosecond durations and unchanged MUSIC label passed.
It used the same NRO SHA-256 as the preceding seven accepted runs:

`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb`

The eighth pair recorded:

| Observation | No scene switches | Ten scene switches |
| --- | ---: | ---: |
| Guest audout calls | 2,224 | 1,902 |
| Calls ≥40 ms | 28 | 21 |
| Calls ≥50 ms | 4 | 2 |
| Lost detailed slow-call records | 0 | 0 |
| Live guest original-SD audit | PASS | PASS |

The no-switch run's largest call was **380,421 μs**, but a byte-level
readback of its original-SD-audited copy identifies it as **audout
attempt 1**: guest begin `77,584,739 ns`, end `458,006,250 ns`,
duration `380,421,511 ns`. It is the **startup call**, before any
music INPUT, not an observed slow call caused by scene switching.
The initial scene trace brackets the first `audoutPlayBuffer`
between original guest submit and return timestamps. This does not
prove an audible underrun during startup.

## Aggregated eight-pair observations

The eight independent same-NRO workflows are:

`39077499594`, `39077898370`, `39078007443`,
`39078024366`, `39078053051`, `39078369183`,
`39078393956`, `39079372486`.

| Measurement | No A/B input | Ten A/B switches |
| --- | ---: | ---: |
| Audout attempts | 17,869 | 15,465 |
| Calls ≥40 ms | 243 | 229 |
| Calls ≥50 ms | 23 | 17 |
| Calls ≥40 ms / 1,000 attempts | 13.599 | 14.808 |
| Calls ≥50 ms / 1,000 attempts | 1.287 | 1.099 |

The aggregate **switch minus idle** difference is +1.209
≥40 ms calls per 1,000 audout attempts, and −0.188
≥50 ms calls per 1,000 attempts. Five of eight pairs have a
greater within-pair ≥40 ms switch rate; three have a greater
within-pair ≥50 ms switch rate.

## Reproducible variability analysis

`tools/analyze_nexium_idle_switch_variability.py` accepts only a
Stage-277 verified same-NRO pair comparison. It first rechecks
the complete accepted per-run counters, valid NRO SHA-256, unique and
ordered workflow identifiers, live original-SD audit flags, total
attempted calls and normalized rates.

For each ≥40 and ≥50 ms band it then computes:

- The exact **within-pair** switch-minus-idle rate difference per
  1,000 actual audout API calls.
- Its median, plus the aggregate rate difference using the actual
  denominators, not an unweighted sum of per-run counts.
- An **all-pairs-minus-one** sensitivity range: no single workflow is
  assumed representative.
- A reproducible 16,384-iteration descriptive whole-pair resampling
  range (fixed PRNG seed 278, preserving each idle/switch pair).

For ≥40 ms calls, the observed leave-one-run-out aggregate rate
difference ranged from **+0.569** to **+2.238** per 1,000 calls. The
whole-pair resampling 2.5th to 97.5th percentile range was
**−1.524 to +3.742** per 1,000 calls.

For ≥50 ms calls, the corresponding leave-one-out range was
**−0.445 to +0.031**, and the resampling range was
**−0.882 to +0.551** per 1,000 calls.

**Neither resampling range is a formal inferential confidence
interval or a randomized permutation test.** They are descriptive
sensitivity analyses only. Every paired workflow ran the
switching half **before** the no-switch half, and the audio calls
within each run are correlated. This fixed order and the host's
variable emulation scheduling are unremoved confounders. No
causality or physical output claim follows.

## Accepted CI

The independent
[Stage278 workflow](../.github/workflows/nexium-eight-pair-variability.yml)
looked up eight prior successful NeXium Actions runs **from this
repository**, downloaded their evidence from GitHub, reverified
original-SD verdicts and every copied source CSV (the ephemeral
runner-original cannot be reopened retrospectively), then ran
the Stage278 whole-pair variability analyzer.

[Actions №39080141701](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39080141701):
**SUCCESS**, including the complete `paired-rate-variation.json`.
The `nexium-verified-eight-idle-switch-pairs` artifact contains
that file, the eight-pair input report, source run identifiers and
repacked archive hashes.

Negative controls in
`tests/test_analyze_nexium_idle_switch_variability.py`
reject duplicated or altered run IDs, forged NRO hashes, wrong
original-SD flags, impossible per-band counts, changed total
denominators, forged normalized rates and unsupported randomized or
hardware assertions. [Host SPU run 39080023988](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39080023988)
passed the new test suite.

## Next meaningful controlled experiment

Future comparisons should **exclude or label the first audout
startup call separately** and match the same steady-state guest
window range (e.g. seconds 1–52 in both halves), rather than mixing
cold-start outliers and differing session durations. A later
randomized/reversed scene-versus-idle run order would help
distinguish effects of experimental order from music transitions.
Neither change would, by itself, test physical speaker output.
