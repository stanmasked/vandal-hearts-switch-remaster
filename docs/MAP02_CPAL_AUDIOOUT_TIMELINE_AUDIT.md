# MAP02 Stage277 — validate CPAL and guest AudioOut counter timelines

**Research-only Draft / DO NOT MERGE.** This is a child of [Stage276 Draft PR #292](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/292), frozen at `6d24825f45f286dc3ec109d25c0abbc9f864e59d`. It does not change any game, ROM, audio data, NeXium source or released emulator.

## Why it matters

Stage273 verified that, **under the sampled Linux host workload**, the 48-kHz ALSA stream gained **zero new write operations after first game input** in three failed 21-ms tests, versus thousands of writes in three successful 22-ms tests. The game was entering one `audoutPlayBuffer` with no return by its prejoin screenshot in the failed cases. This does not establish whether the Rust CPAL game output callback itself stopped running, entered without completing, or ran while lacking guest AudioOut buffers.

Stage274 prepared **Linux opt-in, atomic-only counters inside the CPAL F32/I16 game stream closures**, plus kernel AudioOut append/accepted-frame/release counters. The new binary build is deliberately a separate, changed host condition from the earlier nightly binary and the ALSA preload experiments.

## Exact reporter format

Stage274's periodic reporter writes one CSV row per sample, nominally 200 ms apart and for at most **240** samples:

`T,monotonic_ns,cpal_entries,cpal_returns,cpal_output_frames,sink_consumed_frames,audioout_appends,audioout_accepted_frames,audioout_releases`

All are cumulative atomic counters in one host process. No original audio bytes, game image, raw pointer addresses, music files or PCM samples enter the reporter.

The Stage277 analyzer, `tools/audit_map02_cpal_audioout_timeline.py`, checks:

- Every raw line has exactly nine columns, all counters are unsigned, the host clock strictly increases, no counter decreases and CPAL returns **never exceed** entries.
- At least eight real snapshots, a minimum one-second observed interval, no heartbeat gaps over two seconds, and at most 240 samples.
- For a guest-specific outcome report, the host reporter must begin at least 500 ms before the first controller input and have a sample during the final second before the last guest observation.
- Deltas are computed strictly from the latest pre-input counter snapshot to the latest sampled snapshot **before the final observation**. No baseline or missing temporal context produces a claimed zero.
- Explicitly distinguish (a) no new CPAL callback entries since game input, (b) one or more entered callbacks still unmatched by a return at the last sampled observation, and (c) callbacks with matching cumulative entries/returns.

The third category is evidence of *callback liveness as of the snapshot*, not evidence that accepted guest AudioOut PCM was delivered. Likewise a currently unmatched callback is **not a proven permanent deadlock**: it may still be running at the sampling instant.

The parser is **not itself an archive provenance verifier**. In the eventual real six-guest experiment it must be paired with the independent exact source/binary SHA-256 receipt, run attempt, original NRO, optical PNG CRC-8, raw virtual PCM checks and per-stream ALSA counters. It intentionally returns `trace_bound_to_source_binary_sha256_by_this_parser=false` and `guest_audioout_deadlock_proven=false`.

## Offline CI evidence

The separate workflow `map02-cpal-audioout-timeline-audit.yml` operates only on 16 ROM-free generated scenarios, testing repeated/no calls, pending callback returns, bad chronology, truncated samples, invalid counters, false AudioOut release deltas and missing input/final coverage. It also runs the real CLI against generated data and uploads that synthetic receipt.

**Passing Stage277 proves the parser handles its declared cases; it does not prove a new NeXium executable was built or booted, nor demonstrate any real 21/22-ms CPAL behavior.**

The actual runtime gate will require separately compiled and SHA-pinned NeXium Linux host artifacts and new six-trial guest evidence. No produced result is portable to physical Nintendo Switch DACs without independent hardware testing.

**No merge to main.**
