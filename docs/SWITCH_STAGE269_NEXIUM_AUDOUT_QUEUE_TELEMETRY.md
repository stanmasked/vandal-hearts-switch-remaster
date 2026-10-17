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


## First successful same-run NeXium queue capture — 39064984112

[Full workflow 39064984112](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39064984112), built from commit `1566bf2ca366a15ece89579ca67130f19aa50061`, completed successfully with the **same-workflow NRO**. The downloaded `integrated-nro-preflight.json` independently records `run_id=39064984112`, `nro_sha256=60dc486339331de6c5d24f6e2b049c8ba24ee095a8534746af9f42d18a8a1b91`, and the same commit SHA. The archive contains a guest-original `audio-audout-queue-0000.csv`, exported on guest SD, 2,065 bytes, SHA-256 `954cbe179d4e66312adf087b75be6d460def08d3b53124b477e3102c9c875a5f`. The independent copy matched these bytes. The guest producer's separate receipt reported `export_status=0`, `path_present=1`, `file_size=2065`.

The strict `GUEST_SD_AUDOUT_TELEMETRY_CONSISTENT` audit established **53 consecutive guest-second buckets, 1,935 real audout submit/return observations, 1,935 exact descriptor returns, 0 failed attempts, 121 successful pre-submit queue-service queries, 0 queue-query failures, 0 clock reversals and 0 overwritten windows**. The maximum guest blocking call duration was **52,093 microseconds**. All 121 pre-submit queue samples reported zero; these are explicitly *not* measurements of DAC starvation or audible underruns. The optical/SD scene auditor independently confirmed ten scene changes, 53 scene event rows and 61.035 seconds of host-observed PCM with no clipped samples.

**Historical report limitation:** the `soak-verification.json` in this successful run still contains a stale *hardcoded* `guest_nro_sha256_pinned` field referring to the old build. The downloaded preflight independently and correctly identifies the actual newer NRO. The scene and queue audits passed with actual scene CSV and PCM files, but this outdated output field is not valid provenance of the executed binary. Subsequent commits remove this constant and require the dynamic same-run NRO preflight to be bound into the scene audit; this follow-up itself requires a new green NeXium run before marking its metadata correction verified.

A separate run `39065010229` of a tests-only later commit passed NRO build and audio/scene PCM checks, but failed earlier on the optical exit capture: NeXium never rendered the expected magenta frame. The host harness used a very brief `xdotool key` Plus event which can be missed across guest HID polls. A subsequent fix holds the *real* Plus key for 250 ms, retaining the exact same strict optical/SD audits; no fixture/image substitution is permitted. This needs its own follow-up validation.

**Physical console:** HARDWARE NOT TESTED. No end-to-end DAC, real underrun or audible speaker claims follow from these guest observations.
