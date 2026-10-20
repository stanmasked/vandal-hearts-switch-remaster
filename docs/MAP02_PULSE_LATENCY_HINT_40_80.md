# MAP02: longer host PulseAudio client-latency hints (40 / 80 ms)

**Research-only Draft**, child of frozen [Draft PR #227](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/227) at `72ac0361070421330d34145ff53b13800d5fb4fe`. No game, native audio, DSP, original music assets or physical Switch setup is modified.

## Motivation from genuine NeXium A/B runs

The [first A/B workflow #39351921895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351921895) ran the exact same research NRO once per setting:

- `PULSE_LATENCY_MSEC` unset: eight CRC32/FNV64-exact PCM pages, valid `VHPRE001` guest receipt, 482,099 nonzero 16-bit monitor samples.
- `PULSE_LATENCY_MSEC=20`: missing final guest receipt, all 858,746 recorded stereo frames **zero** in the 48-kHz s16le virtual monitor.

[Repeated A/B #39382937743](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39382937743), source `1ee8616a`, produced **two successful default controls and two failures at 20ms**:

| Guest latency hint | Repetition | Guest CRC | Virtual PCM16 nonzero samples | RMS |
|---|---:|---|---:|---:|
| unset | 1 | passed | 547,806 | 445.163877 |
| unset | 2 | passed | 502,161 | 443.309445 |
| 20 ms | 1 | failed; normal game grid on screenshot | 0 | 0 |
| 20 ms | 2 | failed; normal game grid on screenshot | 0 | 0 |

All five runs used generated content and a 48,000-Hz two-channel PulseAudio null sink. An ALSA plug-in `float32le 2ch 48000Hz` sink input was visible in both conditions; its measured **buffer latency** was approximately 10.7ms in the 20ms failure trials, versus ~29–31ms in the successful default trial snapshots. This demonstrates a repeatable *association* in this emulator/headless-host configuration, **not** exclusive causality or speaker behavior.

The two 20ms recordings were independently downloaded and checked byte-by-byte:
- Repeat 1: 1,231,637 stereo frames, zero nonzero PCM16 samples; SHA-256 `4fec137fb597701ab89d383eb3a4599a32f3ceb11a7a8f759651a3b332552471`.
- Repeat 2: 1,057,690 stereo frames, zero nonzero PCM16 samples; SHA-256 `913872b13995dcff46e1e847f76bc63414c16203181c628ec6b1f3aa8aad2047`.

The earlier first failed screenshot and both repeated late screenshots showed the normal MAP02 tactical board, not the magenta `VHPRE001` packet, even after five extra seconds. We do not know whether the guest is blocked in a NeXium audout API call or whether a backend producer stopped feeding the sink. An emulator dashboard reporting 0 FPS on a still image does not, by itself, establish a deadlock.

## Controlled next question

Does **increasing** the per-client PulseAudio latency hint to **40ms** or **80ms** restore the actual NeXium guest audio and eight-page optical receipt? To test that:

- Change only the opt-in GitHub Actions matrix `latency_ms: [40,80]`, each **repeated twice** on independent runners. The same SHA-256-verified NRO is used in all four jobs; the separate `parec` monitor recorder remains at its default settings.
- Preserve exact source commit SHA, NRO SHA-256, all three screenshots (before, after, late), raw `s16le` 48k stereo capture, independent RMS/nonzero/PCM hash JSON, real sink-input snapshots, the strict eight-page optical CRC proof and individual 512-frame zero-gap reports.
- Treat all four guest test results separately. A job passes only if its real `VHPRE001` screenshot contains eight verified, completed, unmodified PCM pages. Nonzero virtual PCM without the receipt is **not** proof of exact PCM identity.
- Compare actual sink-input buffer latency and playback snapshots before drawing conclusions. Any variance across host runners must be considered, even if both 40ms trials succeed.

The experiment **does not** authorize automatic changes to the default audio backend or game timing. It provides no evidence about physical Switch DAC or speakers, original PS1 soundtrack fidelity, or sample-synchronized music cues.

**All parents and main remain unchanged. Keep Draft / DO NOT MERGE.**
