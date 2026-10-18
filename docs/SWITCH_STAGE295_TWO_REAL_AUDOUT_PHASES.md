# Vandal Hearts Remake — Stage295: two REAL phase0 / phase8 queue observations

The query phase is a compile-time research option; phase0 queries
audout service just before attempts 1+16k, while phase8 queries just
before attempts 9+16k. Both receive **real** guest service counts only
on their queried attempts. The same workflow builds two DISTINCT NRO
binaries, SHA-256 binds them to the same commit/run/attempt and captures
two independent original guest SD files in sequence.

Stage294 first authenticates BOTH original guest SD probe journals
with strict original-vs-copy, guest-clock, slow-call, queue and receipt
checks. Stage295 reads only those successfully audited JSON reports
and their separately bound build manifests. It independently rechecks:

- The exact 1-in-16 attempt index sequences and monotonic submission
  timestamps in both runs, and that each has ten music-changing INPUTs.
- All query successes/failures, zero and nonzero observed count
  histograms, and exact slow-call overlap (≥40ms and ≥50ms).
- Separate original guest SD SHA-256 hashes, and **different** baseline
  and phase8 NRO SHA-256 values tied to the same workflow run.
- Explicitly rejects false scheduler/DAC/hardware claims and
  any inferred queue count from unqueried calls.

This comparison deliberately does **not** interpret changes in
pre-submit service counts or slow-call rates as causal results of
phase. Each NRO is a separate sequential run; emulator host load,
guest audio clocks and starting conditions are not held equal or
randomized. A software service count before `audoutPlayBuffer`
is not the actual queue state during blocking or at physical DAC
playback. The goal is auditable phase-specific **observation**,
not a randomized performance benchmark or a real Nintendo Switch
speaker test.

The Stage295 JSON report is archived with all original evidence
under `runtime-evidence/scene-soak-phase8/`.

## Verified Stage295 follow-up

[Successful Stage295 NeXium CI 39121284096](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39121284096)
passed the strict original-SD audits and the new two-phase comparison.
The current-run comparison reported:

| Source-bound real measurement | Phase0 | Phase8 |
| --- | ---: | ---: |
| Query samples | **121** | **121** |
| Successful service queue queries | 121 | 121 |
| Queries with service count 0 | **121** | **121** |
| Queries with nonzero service count | 0 | 0 |
| >=40ms calls on sampled attempts | 3 | 1 |
| >=50ms calls on sampled attempts | 0 | 0 |

[Host C/Python and toolchain 39121284067](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39121284067),
[Host SPU 39121283967](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39121283967),
and [native PCM 39121284007](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39121284007)
were successful on the source revision containing the analyser.

The separate successful Stage294 run **39120751817** saw **0 vs 3**
sampled >=40ms calls instead of the newer run's **3 vs 1**.
The two runs' different results demonstrate run-to-run variation
in these small systematic samples, NOT that either query phase
caused an audio quality or latency change. All actual pre-submit
service queue counts were zero in both runs. No sampled value
can stand in for the unqueried 15 phases or the DAC during playback.
