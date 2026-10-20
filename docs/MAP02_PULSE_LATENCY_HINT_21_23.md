# MAP02: experiment at 21, 22 and 23 ms — guest PulseAudio boundary

**Draft-only read-only diagnostic branch**, child of all-green
[PR #231](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/231)
at `33f4ce16cde160d30a154cca453a7545ed106b26`.
No native game audio code, NRO audio worker, resampler, libnx source or
licensed game/music assets are changed. **DO NOT MERGE**.

## Source observations

[Run #39385763204](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39385763204)
passed **all seven jobs at the same exact SHA**: GCC, Clang, the single
SHA-256/provenance-checked research NRO build, and two guest NeXium trials
for each of 24ms and 32ms. Strict actual guest `VHPRE001` CRC checked
eight post-ramp / pre-`audoutPlayBuffer` PCM pages, with eight individual
byte-exact CRC32+FNV64 matches in the same-run 48k stereo virtual monitor.

| Requested NeXium-only PulseAudio hint | Trial | Guest optical & 8 pages | Nonzero 16bit monitor samples | Monitor RMS | Observed buffer latency during/after |
|---|---:|---|---:|---:|---:|
| 24ms | 1 | PASS | 506237 | 433.343886 | 15999 / 17333 μs |
| 24ms | 2 | PASS | 484096 | 429.489843 | 20020 / 19978 μs |
| 32ms | 1 | PASS | 520934 | 437.300195 | 10666 / 24000 μs |
| 32ms | 2 | PASS | 522122 | 426.363263 | 21333 / 21333 μs |

All seven inter-page regions in each successful recording remained PCM16
digital zero, and the page-start deltas were multiples of 512 frames.
The strict continuous eight-page verdict still says
`NO_EXACT_EIGHT_PAGE_SINK_MATCH` because complete pages were separated by
zero padding. Do not equate successful audio with uninterrupted audio.

Prior historical 20ms experiments comprised three failures (one in
[#39351921895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351921895),
two in [#39382937743](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39382937743)):
no final `VHPRE001` and **every virtual monitor PCM16 sample zero**.
Baseline/default and 40/80ms controls succeeded. This is a repeated
**association** in headless NeXium/PulseAudio, not a universal causal
conclusion for native Nintendo Switch playback.

Importantly, the **successful 32ms trial #1** had an early observed
48k stereo client buffer latency near 10666 μs (the same value noted
at 20ms failures), which grew to 24000 μs later. A **single snapshot**
cannot be treated as host buffer capacity nor as a fixed pass/fail
threshold. The requested client hint, the instantaneous PulseAudio
buffer delay, audout queue length and real DAC are different quantities.

## Narrower six-run matrix

The experiment changes **only** the experimental GitHub Actions workflow
matrix from `latency_ms: [24,32]` to `latency_ms: [21,22,23]`; each
setting gets **two independent repeats** using the same exact-source
SHA-256-verified experimental NRO built once per workflow.

The pre-existing workflow preserves:
- Real `VHPRE001` optical packet with eight CRC/FNV-checked generated
  PCM pages; failure remains failure, never silently downgraded.
- Independent raw s16le, 48k, 2ch PulseAudio `parec` null-sink monitor
  capture and `presubmit-monitor-health.json` with raw SHA256, RMS and
  count of nonzero samples **even if** the optical proof fails.
- Three screenshots (before, after and five seconds later), detailed
  `pulse-sink-input-observed.json` for the uniquely identified real
  2ch/48k NeXium ALSA input (not the 32ch/768k auxiliary stream), and
  exact guest/monitor page offsets plus signed zero-filled frame gaps.
- Unique per-setting/per-repeat artifacts with same-run source SHA,
  NRO SHA256 and workflow run identity.

Compare outcomes within this controlled cohort before reporting a
possible transition. Even two successes/failures at a requested hint
cannot establish a universal threshold, host buffer capacity or the
mechanism of any guest stall. Do not enable a new latency setting in
the shipping game based only on an emulator experiment.

**Limits:** no physical Switch DAC/speakers, original PS1 sound fidelity
or music cue sample alignment verified. Parent PRs and main must remain
unchanged. **Draft / DO NOT MERGE.**
