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


## First NeXium gate: incomplete evidence, not an audio verdict

[Run 39062773722](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39062773722) successfully compiled its NRO and passed the separate ten-transition optical/SD/PCM scene auditor. The published `nexium-runtime-evidence` archive has an **empty** `soak-audout-sd-locations.txt`, no `soak-audout-sd-unverified.csv`, and the queue-accounting step failed on FileNotFoundError. Its original scene SD CSV exists. Thus **continuous audio-buffer measurements are NOT verified yet**; the independent 10-transition result is preserved.

To diagnose the queue export failure without treating missing guest stderr as a result, subsequent versions preserve an exclusively created `audio-audout-export-failure.txt` with the exact guest exporter status when the CSV cannot be committed. The soak capture copies that receipt separately, and the CI gate prints the status before failing. This failure receipt cannot substitute for the missing CSV or satisfy the queue audit.

The strict SD auditor now compares the untouched guest original with its separately copied CSV, rejects duplicate matching originals, symbolic links and hardlinks, and records the SHA-256 of identical bytes. The `--sd-root` and locations manifest are tied to the isolated NeXium directory. Host regressions and NRO build success do not by themselves prove guest queue export success.

**Next:** inspect the first completed runtime capture that includes the failure receipt, fix the underlying exporter condition if necessary, then rerun the full independent queue gate. Do not label Stage 269 verified until the final NRO build **and** the NeXium queue-gate succeed for the same commit.

## Diagnostic follow-up — post-join guest export receipt

The earlier run did not contain an `audio-audout-queue-*.csv` in the NeXium host-mounted guest SD directory. Native/host CI success is insufficient; the completed stage-269 gate still requires the actual guest file.

For the next capture, `source/main.c` writes a bounded `audio-audout-export-result.txt` *after the audio worker has joined*, separate from every optical/event witness. The receipt contains exactly:

```text
export_status=<signed enum result>
path_present=<0 or 1>
file_size=<decimal bytes observed by guest stat>
```

The receipt is generated even on an exporter-reported success, so missing original CSV can be distinguished from failure of guest-side visibility. NeXium capture now inventories the isolated guest SD directory and copies this guest-produced receipt separately. The auditor requires the literal success code `0`, `path_present=1`, and the exact same `file_size` as the original SD CSV, plus original/copy byte equality. Missing receipt, missing original, nonzero error, or mismatched size are hard failures; the system never fabricates missing PCM evidence.

Neither a positive guest `stat` nor matching SD bytes proves survival of power loss, audible output, or device starvation/underrun timing. The original Stage 268 optical/SD evidence is not modified.

**Acceptance remains pending** until a *single workflow run of a single commit* passes NRO build, optical/SD scene consistency, guest export receipt, and the continuous queue audit.


## Root cause confirmed from archived emulator evidence

The later [NeXium run 39064308239](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39064308239) preserved both a complete Stage 268 ten-scene report (53 scene events, 61.018 seconds of host PCM) and an empty audout-CVS source inventory. In the **same archived artifact**, `integrated-nro-preflight.json` identifies the launched binary as the older build of commit `5a50433fb52d905cee074de052820895566143bf`, downloaded from workflow run `39052705390`, artifact `12108202456`. It is **not** the audout-instrumented NRO compiled by its own run at commit `3ee66d1808cf...`. Therefore the missing guest export receipt in this run is an **expected property of testing the old NRO**; it is not evidence that the new exporter failed or returned success.

The specific cause was `.github/workflows/emulator-smoke.yml`: its build job created a current `runtime-smoke-nro` artifact, but the emulator job **ignored it** and downloaded a hard-coded older `vandal-hearts-tactical-with-native-music` artifact. Host tests and the build job passed while the runtime job was executing unrelated bits. The earlier discussion of possible guest export failure must be read as an unproven hypothesis, now superseded by this concrete CI provenance defect.

The workflow now downloads **`runtime-smoke-nro` from the same workflow run** with no external `run-id`. Before emulation, `tools/verify_switch_runtime_nro.py` checks the download against a manifest generated from the active build-job environment: exact Git SHA, workflow run ID and attempt, NRO name/size/SHA-256, and NRO0 structure. It rejects symlinks, hardlinks and extra artifact members. These checks establish same-run artifact byte consistency **within GitHub Actions**, not external attestation of trustworthy hardware or runtime behavior.

The independently preserved optical scene trace and old-binary PCM evidence remain historically valid **for the old NRO only**. The newer audout telemetry still requires a complete same-run NeXium capture and its separate SD CSV/receipt audit. No Stage 269 queue measurements are claimed from the old-binary runs.
