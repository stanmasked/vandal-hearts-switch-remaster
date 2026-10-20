# MAP02: NeXium / PulseAudio host client latency A/B

This is an opt-in child of [Draft #225](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/225),
based on commit `20b463c4a7dacb71708ef9566361e17570a81b6f`.
It preserves all source, NRO code and original assets. **Do not merge.**

## Motivation: repeatable identity and 512-frame *digital silence*

The first three real NeXium virtual-sink captures found all eight native
post-ramp PCM16LE stereo guest pages exactly (both CRC32 and FNV1a64), once,
in order. The pages retain their content, but the host capture starts each
on one phase of a 512-frame grid and inserts *only zero* bytes between them.

| Earlier run | Source | Gap frames between pages | Total zeros |
| --- | --- | --- | ---: |
| 39348805748 | 759f8414 | 467, 1491, 467, 978, 979, 467, 979 | 5828 |
| 39350029853 | c9e9197f | 467, 467, 467, 466, 12243, 467, 467 | 15044 |
| 39350666670 | 85689659 | 467, 979, 467, 466, 467, 467, 467 | 3780 |

This observation implicates pacing or bridging *somewhere* across producer,
NeXium guest audout service, host sound backend, or PulseAudio monitor, but
**does not establish which component inserts the zeros**. An existing
NRO SHA-256 verified identical across the first two runs; all three runs
use the same experimental C audio code.

## Controlled variation, without modifying game PCM

The separate `.github/workflows/map02-audout-presubmit.yml` job runs
two NeXium guest settings, **each independently repeated twice**
(`strategy.fail-fast=false`, 2 × 2 matrix). The extra repetitions were
added after the **first real A/B run #39351921895** found an unexpected
failure with the 20-ms hint:

1. `default`: leaves `PULSE_LATENCY_MSEC` unset for NeXium.
2. `20`: sets `PULSE_LATENCY_MSEC=20` *only in the NeXium client process
   environment*. The separate `parec` monitor recorder retains its default
   latency. Both variants use the **same SHA256-checked research NRO** from
   a single upstream build, same 48,000-Hz stereo null sink module and
   same host capture format.

Each variant and repetition archives a separate artifact to avoid
overwriting or conflating outcomes:

- `map02-presubmit-nexium-guest-proof-default-r1` and `...-r2`
- `map02-presubmit-nexium-guest-proof-20-r1` and `...-r2`

Also capture `presubmit-guest-before-input.png`, the original
`presubmit-guest.png`, and a later guest image
`presubmit-guest-late.png` (extra five seconds). A separate
`presubmit-monitor-health.json` measures frame count, PCM16 sample count,
nonzero samples, RMS and full raw-PCM SHA-256 **even when** the guest optical
decoder correctly fails. The original fail-closed `VHPRE001` checks remain
mandatory and a failed guest receipt can never become a green test merely
because the monitor capture exists.

Both include `presubmit-guest.png` + CRC-checked `presubmit-guest.json`,
raw 48-kHz PCM16LE stereo monitor capture,
`presubmit-sink-parity.json` with eight page offsets, ordered signed gaps,
the count of nonzero bytes *within* the gaps and 512-frame phase.
They also archive `pulse-client-trial.json`, default sink details before
and after the run, server info, and PulseAudio sink-input snapshots after
the guest has booted.

**Important:** `PULSE_LATENCY_MSEC` is only a **host client latency hint**.
NeXium or its SDL/PulseAudio backend might ignore it. Even a changed gap
pattern across independent runners would *not*, by itself, prove the cause,
due to uncontrollable scheduling noise and differences in actual
sink-input buffer attributes. Inspect the snapshots, and collect repeated
trials at the same settings before attributing causality.

## First actual A/B findings, before the repeated matrix

[GitHub Actions #39351921895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351921895)
built the NRO and passed both GCC and Clang host jobs. Its **default guest
passed**, while the **20-ms guest failed** in the calibrated optical decoder
with `Missing magenta trace receipt border`:

- **Default** artifact `12233742364`: real `VHPRE001` with all eight
  pages and exact independent virtual sink CRC32+FNV matches. Raw 48k s16le
  stereo monitor had 795,306 frames / 16.568875 s, 482,099 nonzero PCM16
  samples and RMS 496.914046. SHA-256:
  `b0248d801aa8f7d45f779df34767a060685aba5f76fdc3dae8f05bc7cb72dc0e`.
- **20 ms** artifact `12234430880`: actual screenshot showed the normal
  MAP02 board, not the final receipt. Independently counted *every* sample
  in the raw 48k PCM16 virtual monitor: **858,746 stereo frames /
  17.890542 s, zero nonzero samples, RMS 0.0**. SHA-256:
  `b16f1318ff3a167b6825ef11783270544db1339af24b60a701d44a7e6bd7cf81`.
  The eight known generated guest PCM page fingerprints were absent.
- PulseAudio NeXium ALSA sink-input snapshots show 48k 2-channel input
  buffer latency ~24,333 µs in default versus ~10,666 µs in the 20-ms
  trial. Both also contained an unusual 32-channel 768k-Hz input;
  **that additional input is not unique to the failure**.

**This is one outcome per setting** and not proof that the environment
variable universally causes a hang. The **20-ms virtual sink recording was
genuinely all-zero in that run**, distinct from merely missing a CRC screen.
The repeated matrix checks reproducibility and captures early/late frames
and independent signal health even when the optical receipt is absent.

## Acceptance/limits

Each trial must pass exact-source SHA, artifact/NRO SHA-256, real optical
`VHPRE001` CRC with eight pages and full read-only PCM analysis.
The strict classification may still be `NO_EXACT_EIGHT_PAGE_SINK_MATCH`
with eight independently byte-exact pages. That is evidence of zero
padding, *not* of corrupted guest output, silence on real hardware, or
speaker/DAC playback. No original PS1 soundtrack, audio assets, music
cue sample alignment or physical Switch speakers have been verified.

Keep this child and all parents Draft / DO NOT MERGE. Do not silently
apply any experimental latency hint in the default shipping application.
