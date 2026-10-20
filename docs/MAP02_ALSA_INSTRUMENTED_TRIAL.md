# MAP02 Stage270 — Linux host ALSA API timing (opt-in only)

**DRAFT / NO MERGE.** New experimental branch from Stage269 [PR #266](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/266) at `b029f0c26da7dcf782a6e2ec3bef9eec012c1525`. No Nintendo Switch audio source, gameplay code, private ROM, soundtrack sample, main branch or parent research code was changed.

## Motivation and what is actually measured

Stage265 [run 39411672432](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39411672432) independently confirmed: the same NeXium binary + same guest NRO, but 21-ms hints failed 3/3 before first `audoutPlayBuffer` return and 22-ms hints succeeded 3/3. Stage269 [run 39449956508](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39449956508) then independently reparsed all six raw `pactl` snapshots and **rejected a single monotonic cutoff on the sampled PulseAudio buffer latencies**.

The new Linux host-only `LD_PRELOAD` module intercepts **actual ALSA calls** made by NeXium, using the public libasound C ABI:

- `snd_pcm_hw_params` on successful configuration, recording **negotiated** PCM rate, channel count, period frames and buffer frames.
- `snd_pcm_writei` and `snd_pcm_mmap_commit`, recording supplied/returned frame counts and elapsed `CLOCK_MONOTONIC` nanoseconds.
- Host thread ID and raw monotonic timestamps for at most **256** events per process; no pixel, music, PCM bytes, ROM, pointer, file path or private game data are recorded.

This does **not** directly intercept the Rust CPAL callback. ALSA write duration is not callback execution time; negotiated ALSA hardware-parameter structs behind the PulseAudio ALSA bridge may not equal actual hardware buffer sizes. ALSA `mmap_writei` wrappers may be counted through `mmap_commit`, but uninstrumented transfer variants are possible. Missing hooks are reported as **UNVERIFIED**, not zero real audio or proof of a backend defect.

## Test design

The new `map02-alsa-instrumented-guest.yml` copies the strict six-trial 21/22-ms × three-repeat research workflow, builds **one shared NeXium binary**, the same NRO opt-in witness build and **one shared shim** with SHA-256 manifest. Each guest verifies all digests and the exact `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT` and source SHA before launching.

The module is enabled **only on the NeXium host process** with `LD_PRELOAD` and `VH_MAP02_ALSA_TRACE_PATH`, never on `parec`, `pactl`, scripts, build tooling or the libnx game. Original 48-kHz virtual Pulse sink, input sequence, prejoin guest screenshot and strict CRC receipt checks remain unchanged. Each guest always uploads trace, PCM and PNG evidence, including when strict audio checks fail.

The always-running final audit independently revalidates guest opt-in NRO hash, exact NeXium host binary digest, shim digest, source SHA, run attempt, prejoin PNG CRC-8, raw PCM SHA-256/nonzero count, and all six raw ALSA trace lines against each original parser result. It reports actual observed 21/22-ms ALSA parameters and transfer durations; it **does not require the outcome split to remain unchanged**, because interposition is a new workload.

A generated-only synthetic `libfakeasound.so` with independent fake host links verifies call delegation, successful params (48,000 Hz / 2 channels / 512-frame period / 2048-frame buffer), simulated `WRITEI` and `MMAP_COMMIT` calls, bounded traces and refusal to claim real CPAL callbacks or Switch DAC audio. Nine other tests reject absent data, forged events, impossible call durations, malformed frame counts, absent transfers and buffer configurations.

## Non-equivalence to older uninstrumented runs

The probe calls the runtime linker for original functions, obtains monotonic timestamps and does bounded per-call CSV file writes. **Those operations can materially change host thread scheduling and audio behavior.** Do not combine results with Stage265 as if the guest host workload were unchanged or mistake any apparent recovered/failed 21-ms trials for a fix.

If all traces pass, the result verifies ALSA API observations **under instrumentation only**. A follow-up needs direct NeXium/CPAL callback counters and a no-probe counterfactual, with host clock synchronization to precise guest call entry/return. Physical Switch hardware/DAC and original game music remain outside this CI.

See ALSA's documented `snd_pcm_writei` and `snd_pcm_mmap_commit` APIs:
https://www.alsa-project.org/alsa-doc/alsa-lib/pcm.html

**No auto-merge.**
