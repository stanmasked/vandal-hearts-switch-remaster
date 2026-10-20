# MAP02 host PulseAudio boundary stability: 21 ms vs 22 ms

Draft-only experiment based on PR #234 exact HEAD `fe35356b9285d84561f330725628d41bc9dbfe1c`. No game C, DSP, audio asset, NRO render path or default backend setting changes. Do not merge.

## Confirmed prior evidence

[Run #39386868354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39386868354) completed all 3 host jobs successfully and 6 actual opt-in guest trials:

| Guest client latency hint | Repeats | Guest CRC optical | 48-kHz PCM monitor |
| --- | ---: | --- | --- |
| 21 ms | 2 | Both fail | Both all-zero PCM16 |
| 22 ms | 2 | Both pass | Both nonzero and all 8 individual pages matched |
| 23 ms | 2 | Both pass | Both nonzero and all 8 individual pages matched |

The 21-ms `ALSA plug-in [nexium]` 2-channel 48-kHz input showed 10666 µs observed buffer latency in both the early and late snapshots. At 22 ms, successful runs showed **5832→21666** and **10312→17312 µs**, respectively. This demonstrates that a low *instantaneous* host buffer latency reading is not by itself a proof of a deadlock or buffer-capacity failure. Separate earlier 20-ms trials (3) all failed with all-zero audio, whereas 24/32/40/80 ms each passed in two trials.

A successful run verifies eight individually exact pre-`audoutPlayBuffer` PCM pages present in the 48k stereo PulseAudio null-sink recording. It does NOT prove a gapless stream, because 512-frame quantized zero-filled intervals between pages remained.

## Six new independent guest trials

Change only the research workflow matrix from `[21,22,23] × [1,2]` to `[21,22] × [1,2,3]`. Each job consumes the same-run SHA-256 checked opt-in NRO and saves uniquely named artifacts, all three screenshots, CRC-checked `VHPRE001` guest proof, raw 48k stereo PCM16 monitor samples, numerical signal health even on failure, and the objectively identified PulseAudio stereo 48k sink input latency snapshots.

The original strict optical failure remains a CI failure; the matrix uses `fail-fast: false`, so all six trials can complete.

If the 21-ms / 22-ms distinction repeats, only conclude a **configuration-specific observed boundary**, not a universal PulseAudio threshold, reason for zero padding, proof that Nintendo Switch audio is silent, or cause of NeXium's guest refusal to advance. Further event-timing trace or guest service timing diagnostics will still be required to locate the mechanism.

Parent PR #234 and all ancestors, along with `main`, must remain frozen. Draft / DO NOT MERGE.
