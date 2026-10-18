# Vandal Hearts Remake — Stage329: original PlayBuffer software-call dispersion

## Goal and limits

Two genuine successful NeXium captures have already independently
replayed their original **last sixteen** successful normal guest
`audoutPlayBuffer` software-call histories in [Stage328 CI
#39170070183](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39170070183).
Stage329 analyzes the **distribution of the fifteen preceding call
durations**, rather than relying on one median to characterize each
capture. No audio synthesis or game runtime change is made.

## Source data (guest software clock only)

| Original source | Capture #39166023593 | Capture #39167324026 |
| --- | ---: | ---: |
| Last normal successful software call | 11,225,937 ns | 22,352,500 ns |
| Prior 15 lower-median software calls | 32,154,011 ns | 31,247,083 ns |
| Last minus prior median | −20,928,074 ns | −8,894,583 ns |
| Original retained normal software calls | 16 | 16 |

The previous distribution statistics (min, max, range,
`median_low(abs(previous−median_low(previous)))`, counts of previous
calls faster/equal/slower than last, and the **first possible insertion
rank** among the sixteen calls) are computed independently from the
original source CSVs at CI runtime and are **not known merely from the
median**. They must not be reported as measured until that independent
run succeeds.

The first possible rank is defined as `1 + count(previous_duration <
last_duration)`; ties are placed **after** the final call for this
rank convention. It is a within-sample rank, **not** a causal
classification of audio timing or a hardware latency percentile.

## Strict source and CI checks

- `tools/audit_nexium_stage329_guest_software_dispersion.py`
  calls Stage328's existing source validator against each original
  preserved `audio-playbuffer-history-000.csv`,
  `audio-last-playbuffer-000.csv`, Stage320 JSON and Stage322 JSON.
  Original SHA-256 values for all **four** CSV files must match their
  pinned authentic NeXium artifacts exactly.
- The auditor computes the fifteen individual software-call durations
  from **source-audited original Stage322 rows**. It does not republish
  guest absolute begin/end timestamps or copyrighted assets.
- Twelve positive/negative synthetic tests check exact rank, ties,
  heterogeneous distribution, missing or forged SHA-256, incomplete
  retained history, changed original Stage320 and Stage322 witnesses.
- A separate
  `.github/workflows/stage329-original-playbuffer-dispersion.yml`
  downloads both real NeXium source archives and recomputes the
  statistics on a new runner. The tests are also included in the
  standard Host SPU regression matrix. Neither CI success may be
  assumed while it is queued.

## Strict evidence boundary

An original sampled guest call duration is **software service time**.
Stage329 does not map guest clock time to host PCM sample timestamps,
does not measure DAC or speaker audio, does not identify audible
dropouts, does not prove original PS1 soundtrack fidelity and does not
test physical Nintendo Switch hardware.

The two captured 16-call windows are narrow final-session tails, not a
population distribution. No general latency guarantee, statistical
representativeness, or Plus-induced cause may be inferred from them.
All original Stage304/305 strict tests and guest SPU and
`audoutPlayBuffer` implementation remain unchanged.
