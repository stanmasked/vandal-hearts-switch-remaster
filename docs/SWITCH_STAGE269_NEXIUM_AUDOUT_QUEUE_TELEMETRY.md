# Stage 269 — continuous guest-side audout page and queue telemetry

**Status: implementation landed on development branch; CI/runtime verdict must be read from the run for the final commit.** Native Nintendo Switch remains **HARDWARE NOT TESTED**.

## Why the previous 10-transition observation was insufficient

Stage 268 verified 10 musical scene transitions, 53 event rows, 0 missing scene records and a 61.049-second virtual PCM capture. Its event trace only covered each scene's first audio submission. A zero scene-event drop count cannot establish zero audout failures, device starvation or audible underruns across the remaining audio pages.

## Stage 269 instrumentation

- `vh_audout_queue_record` observes **each regular audoutPlayBuffer attempt**, whether the same PCM page succeeds or is retried following recovery. Each attempt contains its own guest-clock call/return duration and an **exact-descriptor-return** flag. Failed/ambiguous calls are counted separately; retaining the existing lease is required until the old service session exits.
- An additional `audoutGetAudioOutBufferCount` query runs **before one of every 16 attempted submits**. Successful queries record service-reported minimum and maximum queue counts; unsupported/failed queue queries increment `queue_errors` but **never cause audio playback to fail**.
- **No query executes while `audoutPlayBuffer` is blocked**, so pre-submit counts are not real-time occupancy for that blocked interval. One descriptor/one PCM page is in use; a zero pre-submit count must not be called an audio underrun.
- Full-session attempt, return, failure, queue-query, and longest-call totals are retained. A bounded ring stores **128 one-second buckets**, with an explicit overwritten-window counter when an old bucket is replaced. No heap allocation or file I/O occurs in the audio worker's PCM path.
- The new counter stream is **separate from the immutable 64-event scene trace**; adding page telemetry does not exhaust or rewrite its slots.
- After the audio thread joins, the NRO emits a machine-readable CSV to guest stderr (where available) **and** a separate `audio-audout-queue-NNNN.csv` under the virtual SD directory. It is written to an exclusive `.tmp`, closed, byte-for-byte read back against the expected contents, then renamed. The exporter avoids intentional overwrites and leaves existing captures intact.
- `tools/capture_nexium_scene_soak.sh` retains the guest-produced SD copy as `soak-audout-sd-unverified.csv`. CI then independently audits it and writes `soak-audout-verification.json`; it requires consecutive sampled seconds across the soak, `attempts = releases + errors`, matching per-window totals, exactly one queue probe per 16 attempts, and no discarded windows or backwards-clock records.

## Evidence boundaries

The timing is from the **guest monotonic clock** and only covers the blocking `audoutPlayBuffer` API call, **not** speaker-output onset, DAC timing, end-to-end audio latency, or physical Switch behavior. A successful submit/returned lease does not establish that a sound was heard. Queue probe errors can mean unsupported firmware/emulator functionality rather than defective playback. A measured queue depth of zero before the next submit is likewise not evidence of starvation.

A returned page may contain samples rendered before the latest musical cue. Host PulseAudio capture cannot prove actual handheld speaker output. The SD verification proves readable, matching staged bytes, not power-loss persistence or independent optical duplication of the new audout CSV.

The existing stage-268 scene optical/SD dual-channel witness is preserved. The new queue telemetry is a **separate guest-SD observation** and its CI verdict must not be merged into the stage-268 optical witness or misreported as a physical-hardware result.

## Follow-up

Inspect the completed final-commit NeXium run, preserve the original SD queue CSV and validator JSON from the published artifact, compare page accounting against the PCM capture duration and report the distribution of blocking waits and any real API errors. For any audible-underrun assertion, use explicit starvation or audible output evidence instead of inferring one from pre-submit queue snapshots.
