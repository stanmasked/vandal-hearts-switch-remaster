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

The separate `.github/workflows/map02-audout-presubmit.yml` job now has two
independent NeXium guest variants (`strategy.fail-fast=false`):

1. `default`: leaves `PULSE_LATENCY_MSEC` unset for NeXium.
2. `20`: sets `PULSE_LATENCY_MSEC=20` *only in the NeXium client process
   environment*. The separate `parec` monitor recorder retains its default
   latency. Both variants use the **same SHA256-checked research NRO** from
   a single upstream build, same 48,000-Hz stereo null sink module and
   same host capture format.

Each variant archives its own artifact, avoiding name collisions:

- `map02-presubmit-nexium-guest-proof-default`
- `map02-presubmit-nexium-guest-proof-20`

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
