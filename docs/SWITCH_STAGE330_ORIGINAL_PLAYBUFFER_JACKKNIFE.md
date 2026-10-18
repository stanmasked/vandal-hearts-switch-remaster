# Vandal Hearts Remake — Stage330: original PlayBuffer median sensitivity

## Why measure leave-one-out sensitivity

[Stage329 original independent NeXium analysis #39171613825](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39171613825)
verified the previous fifteen source-authentic normal guest
`audoutPlayBuffer` software call durations in two successful
NeXium captures. Those fifteen-call bounded samples had noticeably
different **median absolute deviations**:

| Captured guest software call tail | First original run | Second original run |
| --- | ---: | ---: |
| Median of previous fifteen calls | 32,154,011 ns | 31,247,083 ns |
| Median absolute deviation | 727,969 ns | 5,297,032 ns |
| Last successful software call | 11,225,937 ns | 22,352,500 ns |
| Original previous-15 range | 21,203,073 ns | 25,495,573 ns |
| Last-call first-possible rank among 16 | 1 | 6 |

Stage330 asks a narrower question: **Does the earlier median and the
last call's ordering remain similar when one original previous call is
excluded?** It does not model an unknown population, introduce new
guest measurements, or attempt to convert guest software time into
host-sampled PCM or physical audio.

## Independent replay and computation

`tools/audit_nexium_stage330_original_playbuffer_jackknife.py`:

1. Retrieves two distinct original NeXium artifacts from successful
   [capture #39166023593](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39166023593)
   and [capture #39167324026](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39167324026).
2. Pins **all four** SHA-256 values: each original guest bounded
   `audio-playbuffer-history-000.csv` and original final
   `audio-last-playbuffer-000.csv`.
3. Recomputes the source-audited Stage328 and Stage329 result from
   the **original retained 16 software call rows** and verifies the
   independent original Stage320/Stage322 source receipts.
4. Makes fifteen independent *deterministic leave-one-out
   resamples* of **14 retained earlier calls**, omitting each of
   the original fifteen exactly once. For each, it computes
   the lower median, median absolute deviation (MAD), and
   first-possible rank of the untouched final successful call.
5. Reports min/max of these fifteen recalculated medians/MADs and
   ranks, but **not** absolute guest time stamps, original PCM,
   game data, sound assets or any hardware/acoustic evidence.

`tests/test_audit_nexium_stage330_original_playbuffer_jackknife.py`
provides twelve synthetic acceptance/rejection tests covering
complete omission conservation, uniform and heterogeneous sample
tails, source hash or Stage320/322 report tampering, and an
important counterexample: the last call can be shorter than the
*full* earlier median without being shorter than every median
after removing one of the earlier observations. The auditor
**preserves this authentic sensitive observation**, reports its
Boolean stability flag as false, and does not improperly convert
an exploratory diagnostic into a strict source rejection.

The independent GitHub Actions workflow
`.github/workflows/stage330-original-playbuffer-jackknife.yml`
downloads original source artifacts and publishes only a compact
source-hash-bound summary after validating the original 15/16 calls.

## Evidence limits

These fifteen leave-one-out variants are mathematical sensitivity
checks on two **small, selected, end-of-run software-call samples**.
They are **not independent experimental runs**, statistical
confidence intervals, measures of physical sound, guest-to-host
clock synchronization, or a test of original PS1 soundtrack
accuracy. The script does not change the SPU, audio buffering,
`audoutPlayBuffer`, game logic, or strict original Stage304/305
evidence audits.

The independent Stage330 CI must complete successfully before
source-authentic leave-one-out min/max values can be reported.
