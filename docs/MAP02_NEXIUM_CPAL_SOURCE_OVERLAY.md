# Stage274 — pin the exact NeXium code paths for CPAL/AudioOut tracing

**Research-only Draft. DO NOT MERGE.** Child of [Draft PR #280](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/280) at parent SHA `04b20024a50327091cff430eb5c28e4722d4ec76`. No ROM, licensed game music, production Nintendo Switch audio code, parent PR, or released emulator binary changes.

## Why this stage is needed

Stage273's [actual guest evidence](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39460035568) confirms that under 21-ms requested Pulse latency, the guest entered the first `audoutPlayBuffer` (1/0 at the prejoin snapshot), virtual nonzero PCM remained zero, and the 48-kHz ALSA instance recorded **no extra write or frame transfer in the sampled window after guest input**, despite other ALSA streams continuing. At 22 ms, guest CRC/PCM succeeded all three times and the 48-kHz ALSA instance advanced.

That contrast does **not** identify the reason for the missing guest buffer release or lack of 48-kHz host activity. In particular, a low-level ALSA write count cannot determine whether CPAL failed to invoke its Rust output callback, the callback itself entered and blocked, or the AudioOut service did not submit eligible samples.

## Exact upstream NeXium code review

Read the **actual public NeXium source** at immutable Git commit `089562567a0a8760dfdd8420e1f57c35159a9219`:

- `nexium-runner/src/audio.rs`: `device.build_output_stream` uses distinct `f32` and `i16` CPAL output closures which call `drain_stereo_to` / `drain_stereo_to_i16`; a `HostAudioSink` uses `AudioOutMixer` and host-consumed counters. The callback reads and writes some mixer state through a mutex. A low-cost *atomic* counter before/after each callback can distinguish no callback invocation from an incomplete callback.
- `nexium-gui/src/ui_audio.rs`: a **separate** CPAL output stream handles UI music/sound, so the additional host audio activity is not automatically the game's 48-kHz AudioOut stream. The earlier measured 768-kHz/32-channel ALSA configuration is not definitively assigned to UI audio solely from this source structure.
- `nexium-kernel/src/services/audio_out/handlers.rs`: buffer completion depends on audio consumed frames when the host stream is available, otherwise a due-time fallback; buffer submission/release and consumption need separate observation.

**Critical provenance caveat:** the immutable source revision above was obtained by GitHub code search, **not** authenticated as the source revision that built the archived `nexium-nightly` binary. A rebuilt host executable, even from these pinned sources, is a new experimental condition. No historical SHA-256 equivalence is claimed.

## Prepared opt-in overlay

`tools/prepare_map02_nexium_cpal_overlay.py` accepts only the above immutable SHA and a clean upstream tree. It modifies exactly **three files inside an isolated CI checkout**:

1. The runner CPAL F32 and I16 closures: atomic callback-enter/callback-return and frames-written counters. No syscalls, mutexes, logging or allocation are added **inside** a real-time callback.
2. A dedicated non-real-time Linux-only reporter at nominal 200-ms intervals. CSV snapshots include monotonic host ns, CPAL callback entries/returns, output frame counts, sink-consumed frames, and kernel AudioOut accepted appends, accepted frames and released buffers. The path must be opt-in, absolute and no longer than 800 chars; at most 240 snapshots.
3. The kernel AudioOut acceptance and release locations and a Linux-only `libc` dependency for host monotonic time.

The source tool refuses unknown/dirty upstream revisions, duplicate injection or missing anchors and writes a manifest containing original/new source SHA-256 for each file. Existing CRLF line endings are preserved to prevent unrelated modifications.

CI tests synthetic ROM-free patch targets, downloads exactly the immutable upstream revision into a **separate** checkout, applies only these three modifications, verifies scope and manifest, checks Rust parsing via `rustfmt --emit stdout`, checks Cargo workspace metadata, and uploads a source diff artifact.

## What passing this CI does *not* prove

- **Not a Rust cargo check** and not a runnable instrumented NeXium binary.
- **Not** the same binary as archived same-NeXium 21/22-ms trials.
- No CPAL callbacks, guest audio, guest IPC returns or real-time audio are measured in this source-only stage.
- The kernel/host instrumentation changes timing if used in future; any rebuilt emulator requires a new controlled paired workload with immutable host/probe SHA hashes and real guest PNG/PCM artifacts.
- Neither an infinite guest deadlock, production repair nor physical Nintendo Switch DAC/speaker output is verified.

A follow-up build can validate Rust types and then reproduce the 21/22-ms A/B with this **new** instrumented NeXium build. Only then should CPAL entered/returned counters be compared to AudioOut appends/releases and per-stream ALSA writes.

**Parent branches and real game audio are unchanged.**
