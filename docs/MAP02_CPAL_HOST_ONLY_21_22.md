# MAP02 Stage286 — host-only 21/22-ms CPAL control, no guest NRO

**Research-only Draft / DO NOT MERGE.** Child of [Stage285 Draft PR #328](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/328), frozen source `8177b825f76dac26b2abebe81b7c42fa2b167c68`. It changes no game code, compiled NeXium executable, research NRO or historical audio/PNG evidence.

## Why this comparison is newly informative

[Stage285 Actions #39484483401](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39484483401) **SUCCESS**, 15/15 generated timing tests and independent analysis of six original real NeXium guest runs. With a requested **21ms Pulse latency hint**, the cumulative CPAL callback count stopped increasing **at least 6.21, 10.00 and 10.17 seconds before the first controller input** respectively. At the requested **22ms hint**, callbacks continued through the input window in all three original guest trials. This establishes that the input action was not the trigger for the initial absence of new CPAL callbacks in the 21ms window, but earlier guest initialization remains a possible contributor.

Crucially, the immutable upstream `nexium-gui/src/main.rs` at commit `089562567a0a8760dfdd8420e1f57c35159a9219` invokes `audio::init_host_audio(...)` **before** it processes `std::env::args().nth(1)` to obtain an NRO path. Therefore the host audio stream can be created without launching any guest software.

## Narrow Stage286 causal discrimination: no NRO at all

Launch the **identical already compiled, source-verified** NeXium ELF SHA-256 `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0` **without any NRO, ROM, firmware or game music**. Four independent Linux runners cover 2× requested 21ms and 2× requested 22ms, in the same Xvfb/soft Vulkan/Rustarmic/virtual PulseAudio 48-kHz sink environment.

Each launch has a clean HOME, `NEXIUM_CPU_BACKEND=rustarmic`, and a fixed `VH_MAP02_CPAL_TRACE_PATH` to record the actual Rust CPAL callback entry/return and output frame counters. Once the empty NeXium GUI is visible, record a **host-only observation marker** and capture roughly 20 seconds of subsequent callback snapshots, plus a second host marker and actual visible-window PNG. The NeXium command is exactly `"$HOST_ELF"`, not `"$HOST_ELF" "$NRO"`. No controller command is sent, and no guest `AudioOut` event is expected.

The existing verified bounded CPAL/AudioOut parser re-checks host CLOCK_MONOTONIC coverage, with those two neutral **host-only** observation markers substituted for the parser's original guest markers. The final host-only result renames the source fields to avoid claiming any guest input took place. Each job independently verifies the actual ELF SHA and archives its own 200ms reporter CSV, screenshot, log and source manifest.

A separate auditor downloads all four original job archives, checks exact host identity, requested-hint labels, independent run/repeat numbers, actual callback count deltas and image evidence. Nine ROM-free synthetic tests reject duplicate jobs, altered hashes and inconsistent or mixed results. If 21ms again yields no new callbacks during observation and 22ms yields continued callbacks **without any guest code present**, then the observed requested-hint effect demonstrably occurs in the host-side audio pipeline independent of guest `AudioOut` commands.

## Strict limitations

A host-only 21/22ms contrast still does **not** identify which PulseAudio, ALSA, CPAL or scheduling operation is causally responsible. The requested `PULSE_LATENCY_MSEC` is not a measured device period. Host-only testing does not prove an infinite deadlock, original PS1 music fidelity, a Nintendo Switch hardware audio result or a production-game fix. If the no-ROM contrast disappears, that is important counter-evidence: the earlier guest initialization, UI behavior or timing may matter, and it must be reported as mixed rather than hidden.

**No original assets in GitHub. All upstream and game branches remain unchanged and unmerged.**
