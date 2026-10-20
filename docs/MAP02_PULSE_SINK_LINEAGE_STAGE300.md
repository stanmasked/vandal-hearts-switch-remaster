# MAP02 Stage300 — independent real PulseAudio sink-input lineage

**ROM-free / research-only / Draft — DO NOT MERGE.** Parent: successful [Stage299 Draft PR #381](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/381), pinned head commit `fb7f3d9d0b7a25cb4a4cf067abcaf0f2fe92bfc4`, successful original [Actions #39511807796](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39511807796), both 21ms and 22ms genuine NRO trials.

## New archived evidence

Original Stage299 preserved TWO host-side `pactl list sink-inputs` text snapshots: `pulse-sink-inputs-during.txt` taken before guest keyboard input and `pulse-sink-inputs-after.txt` taken late after the guest interacted with AudioOut. These files were **not** previously included in a source-bound independent comparison even though they were collected during the original successful NeXium run.

Both screenshots' host-side records show exactly two sink inputs attributable to the same NeXium process, one `float32le 2ch 48000Hz` and one `float32le 32ch 384000Hz`, on the same Pulse server/sink with stable per-profile client IDs. Both connections have `Corked: no`, `Mute: no` at both sampling points. The 32-channel/384-kHz entry is an actual observed NeXium-created Pulse profile; **it is not evidence of a desired emulator game output format or a Nintendo Switch hardware sample rate**.

The original snapshots show:
- **21ms:** 2ch/48k Pulse sink input `#2 → #2`, 32ch/384k `#94 → #94`. The independent CPAL/L guest observation recorded **0 new CPAL callbacks after input**, guest prejoin `ENTERED_PLAYBUFFER`, 0 nonzero virtual PCM16 samples. Pulse nevertheless showed both sink inputs **uncorked** at the two observed moments.
- **22ms:** 2ch/48k Pulse sink input `#2 → #14`, 32ch/384k `#11 → #11`. The independent CPAL/L guest observation recorded **2,242 new CPAL entries after input**, 851 CPAL error callbacks, original generated NRO CRC **8/8**, and **492,050** nonzero virtual PCM16 samples. The changed 2ch sink-input number shows a PulseAudio connection identity replacement between the two snapshots; it does **not** identify the component that caused the replacement, when it happened, or whether it is causal for guest audio.

## Independent falsification

Stage300 re-downloads only the two **immutable Stage299 artifact names** from exact original Actions run `39511807796` and does NOT re-launch NeXium or rebuild it. The auditor verifies the actual compiled new Stage298 ELF SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a`, unchanged generated research NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`, source run/attempt/hint receipts, fresh monotonic P/L CSV audit against archived original, original virtual PCM bytes SHA and original verified guest receipts.

The Pulse parser rejects duplicate or extra sink inputs, wrong audio profile, missing/ambiguous `Corked` status, non-NeXium application, mismatched process attribution across snapshots, changed per-profile Pulse client/sink, or malformed files. It checks raw snapshot hashes but **redacts** PIDs, usernames, hostnames and raw process properties from published JSON. Generated-only tests include falsifications of changed IDs, corked states, sample formats, ownership and incomplete source snapshots.

## Interpretation boundary

A PulseAudio sink input marked `Corked: no` means that *PulseAudio reported it uncorked at one snapshot*. It does **not** prove the CPAL data callback is repeatedly running, that ALSA is generating frames, that the corresponding input is precisely the game's audible stream, or that no backend pause occurred between snapshots. Likewise, `#2 → #14` is a source-observed change in a Pulse sink-input identifier, **not proof of a CPAL stream drop/rebuild, xrun recovery, audio-fix mechanism or the audio root cause**.

Two runs do not prove a reliable 21/22ms hardware boundary. The 21 and 22 values are requested Pulse latency hints, not measured device periods. No original PS1 soundtrack, permanent guest deadlock, physical Switch DAC or production fix is established. All four additions are isolated research auditor, tests, CI and this document, without game source, licensed assets or upstream NeXium edits.
