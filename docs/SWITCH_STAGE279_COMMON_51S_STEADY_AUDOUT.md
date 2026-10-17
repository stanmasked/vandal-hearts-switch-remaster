# Vandal Hearts Remake — Stage 279: Equal steady-state guest audio windows

**Objective:** exclude the startup second and compare identical
guest-clock audio-second windows in the eight accepted same-NRO
idle/switch NeXium pairs.

**Real hardware / speaker output: NOT TESTED.**
This measures blocking `audoutPlayBuffer` software-call durations,
not soundtrack authenticity, DAC underruns or causal effects.

## Why common seconds 1–51?

[Stage 278](SWITCH_STAGE278_EIGHT_PAIRED_AUDOUT_VARIATION.md)
compared eight audited pairs using full sessions of unequal lengths:
idle sessions typically had ~61 seconds and switch sessions ~52–53.
In the final idle run the *first* `audoutPlayBuffer` call alone
lasted 380.421511 ms. That is startup, not a music transition.

A retrospective inspection of all eight independently captured
guest latency CSVs found that one accepted switch-side run
contained only **52 complete second buckets** (0 through 51).
Therefore the longest genuinely identical interval available
across all 16 captures is **guest audio seconds 1 through 51,
inclusive** (51 full one-second buckets).

Using 1–52 would silently omit that run's missing final second,
and using second 0 would introduce cold-start behavior. The new
analysis refuses missing seconds rather than filling or interpolating
them. The original guest monotonic clock is anchored by the
independent first audout submit/return events in each run;
these are equal *relative audio-service age* windows, not aligned
physical DAC clocks.

## Independent archive reanalysis (accepted in GitHub Actions 39080694548)

The first separate byte reanalysis used the same eight GitHub Actions
archives that passed [Stage278 independent archive CI
39080141701](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39080141701).

| Guest API-call measure; seconds 1–51 | No A/B scene switch | Ten A/B switches |
| --- | ---: | ---: |
| Individual audout calls | **15,039** | **15,005** |
| Calls ≥40 ms | **203** | **215** |
| Calls ≥50 ms | **17** | **16** |
| ≥40 ms calls / 1,000 attempts | **13.498** | **14.329** |
| ≥50 ms calls / 1,000 attempts | **1.130** | **1.066** |

The ≥40 ms normalized rate difference (switch minus idle) is
**+0.830 per 1,000 attempts**, compared with **+1.209**
for the unequal complete eight-run sessions. The ≥50 ms
difference is **−0.064 per 1,000 attempts**.

The use of a fixed 51-second window removes the initial 380 ms
API-call spike and removes tail-duration imbalance, but does
**not** remove experimental-order, host CPU, guest scheduler or
emulator virtualization effects. Do not interpret this difference
as a causal music scene effect.

## Reproducible fail-closed tools

`tools/analyze_nexium_steady_state.py` accepts 2–12 source
evidence archives previously eligible for Stage277 original-SD-bound
full-record comparisons. It first executes
`audit_pair_archives` on the complete original-SD-audited
copies, including the prior valid writer receipts, same NRO, scene
trace, no-A/B input control and absolute guest audio time origin.

Then, for **each** of the two modes in each run, it independently:

1. Parses and verifies the complete guest latency CSV and independent
   guest origin clock.
2. Rechecks every individual ≥40 ms begin/end timestamp against
   original second-by-second call ordering, per-second buckets
   and exact ≥50 ms classification.
3. Requires all 51 selected second buckets 1–51, omitting both
   startup second 0 and nonshared trailing idle windows.
4. Recomputes counts and verifies the selected timestamps equal
   the selected per-second histogram counts — without estimating
   missing or unpublished slow calls.
5. Records excluded first-second calls separately (including any
   captured first-call duration) so cold-start outliers remain
   visible rather than discarded silently.
6. Normalizes by actually attempted buffers inside precisely
   those 51-second windows and runs whole-pair descriptive
   variability analysis, retaining nonrandomized/no-audio
   boundaries.

Negative regressions in
`tests/test_analyze_nexium_steady_state.py` reject missing windows,
altered CSV files, different NRO identities, duplicate workflow
IDs and fake slow-call index/duration conservation.

CI support was added to the Host SPU and native NRO smoke jobs.
The separate
[`nexium-eight-pair-variability.yml`](../.github/workflows/nexium-eight-pair-variability.yml)
also downloads all eight successful NeXium runs, reaudits their
original-SD-bound archive copies, computes the standard complete-run
comparison and publishes the new matched-second result as
`steady-state-only-s1-to-s51.json`.

**Evidence boundary:** the CI has previously audited the original
runner SD files *while the runs were live*; this retrospective tool
can only reopen the archived source bytes and their earlier verdicts.
No statistical confidence interval, randomized scene intervention or
physical Switch audio result is claimed.

## Completed Stage279 independent verification

[GitHub Actions 39080694548](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39080694548)
successfully checked **all eight source archives** and generated
`steady-state-only-s1-to-s51.json` in the downloadable
`nexium-verified-eight-idle-switch-pairs` artifact.

The strictly revalidated result was
`ORIGINAL_SD_BOUND_COMMON_51S_AUDOUT_REVERIFIED` and exactly
15,039 idle versus 15,005 switch-side audout attempts.

Whole-pair descriptive variability, with 16,384 reproducible
entire-pair resamples, gave the following results per 1,000
guest audout calls:

| Duration threshold | Aggregate switch-minus-idle difference | Leave-one-pair-out range | Descriptive paired-resampling percentile range |
| --- | ---: | ---: | ---: |
| ≥40 ms | **+0.830** | +0.103 to +2.025 | −2.044 to +3.318 |
| ≥50 ms | **−0.064** | −0.301 to +0.156 | −0.789 to +0.606 |

Among the eight within-pair differences, five were positive for
the ≥40 ms threshold and five were also positive for the ≥50 ms
threshold (the identity of positive pairs need not be the same).
Both paired-resampling sensitivity ranges cross zero. These are
**descriptive**, not statistically valid randomized causal-effect
confidence intervals. Each NeXium workflow used a fixed
switch-then-idle capture order.

The Stage279 report separately preserves the excluded second-0
counts and first observed call. In run `39079372486` the original
idle startup call had duration `380421511` ns; that event is
explicitly excluded from these steady-state totals. It remains
present in the immutable original source archive and prior
Stage278 report.

No new playable game level, physical Switch test, source-music
fidelity validation or actual-audible-underrun measurement is implied.
