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
