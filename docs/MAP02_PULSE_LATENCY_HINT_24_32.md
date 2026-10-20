# MAP02: narrow PulseAudio client-latency experiment (24 versus 32 ms)

**Draft-only, ROM-free diagnostics.** Child of green [Draft PR #229](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/229) at `8e33d01b2eec9d84f38a75ce83650ca20b36aeff`. No source changes to the guest audio worker, resampler, SEQ/SPU, libnx, music assets or standard game build. **DO NOT MERGE**.

## What is already confirmed by actual NeXium trials

The same opt-in source build and 48-kHz stereo null-sink monitor were used in:
- Three independent 20-ms failures: first [#39351921895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351921895), then twice in [#39382937743](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39382937743). No final CRC optical `VHPRE001` receipt; virtual monitor **100% PCM16 zeros**, despite NeXium showing the MAP02 grid.
- Two successful default runs in #39382937743: eight independently exact pre-submit guest PCM pages found in the virtual sink; monitor nonzero PCM16 samples 547806/502161.
- **Both 40ms and both 80ms trials passed all seven exact-head CI jobs**, including the real guest optical CRC proof in [#39383939681](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39383939681). All had 8/8 CRC32+FNV1a64-identical PCM pages in the 48k stereo sink and a nonzero monitor:

| Setting | Repeat | Nonzero PCM16 samples | RMS | Sum of seven silent gap frames |
|---|---:|---:|---:|---:|
| 40 ms | 1 | 467591 | 425.363840 | 6852 |
| 40 ms | 2 | 490958 | 438.318090 | 5828 |
| 80 ms | 1 | 573094 | 475.983816 | 4292 |
| 80 ms | 2 | 566397 | 477.017077 | 5316 |

**No full zero-gap eight-page chain** has been established. All individually exact PCM pages begin on a shared 512-frame phase *within each recording*, and all inter-page gaps remain PCM16 digital zero. Physical Switch speaker/DAC audio, original PS1 soundtrack accuracy and music cue synchrony remain unverified.

### Actual PulseAudio host-observed buffers

Independently downloaded and read original signed-in artifacts for 40-r1 and 80-r1. The actual `ALSA plug-in [nexium]` `float32le 2ch 48000Hz` input had these two snapshots:

| Client hint | During, buffer latency | After actions, buffer latency |
|---|---:|---:|
| 20 ms — failed (prior A/B) | approximately 10,666 µs | approximately 10,666 µs |
| 40 ms — succeeded | 21,103 µs | 24,041 µs |
| 80 ms — succeeded | 57,437 µs | 59,312 µs |

The additional `float32le 32ch 768000Hz` ALSA input exists in both successful and failed settings, so it must not be mistaken for the actual 48k stereo playback input or singled out as causal evidence.

These buffer-latency values are **observed**, not the requested `PULSE_LATENCY_MSEC` values, and their readings depend on sampling instant and runner scheduling. Even the correlation of the 20-ms hint with a zero signal is not an isolated mechanism proof.

## Next controlled probe

Only the opt-in GitHub Actions guest matrix changes from `[40,80]` to
`[24,32]`, **twice each**. The independent `parec` recorder, null sink and identical NRO SHA256 provenance remain unchanged. We seek whether the output/receipt success transition lies between these hints.

A standalone Python helper `tools/report_pulse_sink_input_latency.py` now parses the two actual sink-input snapshots and stores `pulse-sink-input-observed.json`, rejecting missing/duplicate 2-channel 48000-Hz NeXium ALSA inputs instead of arbitrarily selecting a 32-channel auxiliary stream. Its generated-only regression tests cover the positive case, missing input, duplicate input and malformed data. The helper expressly refuses to claim that the hint was honored or speaker audio proved.

The CI remains **fail-closed** on NRO/source SHA-256 checks, real guest `VHPRE001` CRC with 8 pages, independent host tests, and actual monitor PCM analysis. It archives early/final/late optical screenshots, raw PCM16 stereo, SHA-256/nonzero/RMS JSON and host-input details even on failure. Do not count any variant as a pass before the exact-head GitHub Actions result.

No production audio adjustments without further causal evidence. Keep parents #229/#227/#225/#223/#218/#212 and main unchanged; Draft / DO NOT MERGE.
