# MAP02 Stage273 — low-frequency ALSA lifetime counters

**Draft / do not merge.** Child of [Draft PR #277](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/277), frozen parent SHA `d0c3606606898180d31774b9e4d5f80103b43562`. No gameplay source, original ROM, music, Switch production audio engine or parent branches change.

## What the previous stage established

The [Stage272 six-guest run #39456933643](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39456933643) confirmed one NeXium executable, the same opt-in research NRO, one anonymous stream-ID ALSA hook, all six real guest CRC8/PCM archives and two successful independent auditors. Requested 21ms failed strict guest audio 3/3; requested 22ms passed 3/3.

For **the first 256 host events only**, the anonymous-PCM shim found one 48-kHz/stereo transfer in every failed 21ms trial, versus 212, 34 and 63 48-kHz transfers in the three 22ms successes. A 256-event recording saturates early and cannot distinguish a delayed start from a lifetime stall.

## New counter-mode experiment

This research child introduces a **separate** opt-in Linux host preload `tools/map02_alsa_lifetime_probe.c`. It intercepts `snd_pcm_hw_params`, `snd_pcm_writei`, `snd_pcm_mmap_commit` and `snd_pcm_close`, maintaining atomic cumulative write/commit/frame/error counters per anonymous ALSA PCM instance. **No raw pointers, PCM bytes, ROMs, audio samples or soundtrack identifiers are written**. A reporter thread appends counter snapshots nominally every **200ms**, rather than file I/O on every ALSA transfer. A short lock is used to bind a new PCM handle to a process-local ordinal.

This changes workload and host scheduling relative to Stage272, so measured behavior must be described as a new instrumented condition. Sampling overhead is lower in principle but has **not been proven lower on the actual NeXium runner** merely by changing its design.

The experiment uses exactly one SHA-verified NeXium host binary, one SHA-verified probe library, and the same separately opt-in Nintendo Switch NRO distributed to all six guest jobs (requested Pulse hints 21 and 22ms, three repetitions). Strict original guest CRC and virtual PCM checks run before the periodic-counter audit. The six-guest independent final auditor rejects any mismatch in source SHA, run attempt, binary digest, actual PNG CRC-8, PCM raw digest/nonzero count or saved counter report.

## How timing completeness is bounded

Host monotonic timestamps are recorded for the first actual controller input and the last post-input screenshot. The auditor requires heartbeat samples before the first input and through the final observation (allowing at most one second of last-sample uncertainty), strictly increasing counters, and no heartbeat gap larger than two seconds. All cumulative counters must be nondecreasing. Counter values describe *the sampled active lifetime* of an ALSA instance: they do not prove the very final milliseconds because the workflow may terminate NeXium using SIGKILL.

The parser distinguishes stream ordinals and format classifications **48-kHz/stereo / other / mixed**. For every stream with a real pre-input counter baseline and a sampled state near the final screenshot, it now reports **input-to-final write/frame deltas**. When the stream was first seen after the input marker, that delta is explicitly `null` (unknown), **never fabricated as zero**. A missing stream or missing sampling coverage is reported as UNVERIFIED, not as zero traffic. Synthetic fake-ALSA tests validate actual dynamic symbol delegation, thread snapshots beyond the old 256-event cap, tampered counters, missing heartbeat, bogus stream classification and guest marker coverage.

### Interpretive constraints

- A stalled guest `audoutPlayBuffer` observation is not proof of permanent service deadlock.
- A PulseAudio/ALSA transfer counter is not a Rust CPAL callback count.
- `LD_PRELOAD` still modifies the host workload, even without per-transfer file I/O.
- A 200ms snapshot is **not** a sample-aligned observation of the guest's audout call.
- No Nintendo Switch physical DAC or original PS1 soundtrack fidelity is tested.

**No automatic merge and no change to the working game audio transport.**
