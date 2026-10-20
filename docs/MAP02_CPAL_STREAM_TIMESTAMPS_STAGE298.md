# MAP02 Stage298 — separate Linux-host CPAL lifecycle timestamps

**ROM-free / experimental / Draft — DO NOT MERGE.** Child of [Stage297 PR #374](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/374). Scope limited to four research-only files. The underlying game, original PS1 assets, NeXium upstream repository, original guest research NRO, and `main` are untouched.

## Observed motivation: Stage297

[Stage297 Actions #39507437731](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39507437731) verified five real prior CPAL lifecycle CSV archives: both 21ms trials already had cumulative `cpal_entries=1` at the first snapshot, followed by zero new entries for 31.840s and 33.854s before/after guest input. At requested 22ms, the original generated optical guest returned 8/8 CRC and CPAL entry counters increased throughout the observation. **No previous CSV captured the exact timestamp of the successful stream-play call** or whether the host CPAL stream was destroyed.

## New experimental host-source probe

Checkout immutable upstream `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219`, apply already-validated Stage274/286 source overlays to 3 allowlisted host/kernel paths, then add Stage298 **only** to `nexium-runner/src/audio.rs` with fail-closed unique anchors. Requires unchanged exact upstream Cargo.lock SHA-256 `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`. Build a new exact-head-tagged Linux x86-64 release ELF with backend-rustarmic; **do not reuse or substitute the Stage287 executable**.

The Linux-only Stage298 stores monotonic CLOCK_MONOTONIC nanoseconds from non-real-time stages: CPAL stream build start, build success/failure, before `stream.play()`, successful/failed play return and lifetime end of the retained CPAL stream via an RAII Drop wrapper. `Drop` is observed only if this application-owned wrapper is actually destroyed. No `Stream::pause()` method is invoked in this source; the absence of such an event cannot prove the OS/backend did not suspend a stream.

If `VH_MAP02_CPAL_LIFETIME_PATH` is a bounded absolute path, the **existing non-audio reporter thread** writes separate `P,sample_monotonic_ns,build_begin_ns,build_ok_ns,build_fail_ns,play_begin_ns,play_ok_ns,play_fail_ns,drop_ns,cumulative_cpal_entries` samples every 200ms. This path is independent of the existing unchanged 11-column `L,...` CPAL/AudioOut CSV. All file writes, time syscalls and configuration happen on non-real-time paths. The F32 and I16 audio callbacks remain byte-identical to Stage286, with only relaxed atomic counters from Stage274.

P's cumulative callback count only brackets *first observed callback increments* between reporter samples — it is **not** an exact per-callback timestamp. Even monotonic event times around `stream.play()` cannot exclude the instrumentation itself changing scheduling. No `Stream::pause()` instrumentation is claimed when the pinned host never calls it.

## Evidence gates

Stage298 workflow:
1. Verifies exactly these four research-only changed files versus pinned Stage297 head `48801459d14169b4ebac4f29806081e8604eefcb`.
2. Type-checks the old source patch tests plus eight new Stage298 source-anchor and real-time invariance tests; applies overlay only after old overlays.
3. Runs `rustfmt` parsing, locks exact original dependency graph, compiles a genuinely new optimized Linux NeXium/Rustarmic ELF, validates embedded opt-in reporter switches and SHA-256.
4. Saves fresh isolated binary/source receipt and build logs, without ROMs/audio tracks. A **subsequent independent test** must run that new ELF with original opt-in NRO at both 21/22ms before claiming P events actually execute.

Any source failure, mismatched locked dependencies, missing reporter symbol or build error is **UNVERIFIED**. No compilation-only result establishes the 21ms cause, a CPAL stream pause/drop, original PS1 soundtrack playback, Nintendo Switch DAC sound, emulator production repair, or causal relationship between P timestamps and guest state.
