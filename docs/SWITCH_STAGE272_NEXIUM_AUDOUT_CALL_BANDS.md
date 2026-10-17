# Vandal Hearts Remake — Stage 272: per-call audout latency histogram

**Experimental guest-emulator-only instrumentation. No real Switch tested.**

## Why

Stage 271 measured one maximum blocking \`audoutPlayBuffer()\` call
per guest second, but did **not** count how many calls were slow. A
per-second maximum above 50 ms only proves *at least one* such call.
Stage 272 adds deterministic per-call counting directly to the existing
fixed-size, single-writer audout telemetry; it does **not** collect a
malloc-backed event trace or format CSV in the PCM callback.

## Measurement and outputs

For every actual attempted \`audoutPlayBuffer()\`, measured from the
guest monotonic clock, exactly one of four nanosecond-qualified latency
counters increments:

| Band | Duration |
| --- | --- |
| \`lt25ms\` | Less than 25,000,000 ns |
| \`from25to40ms\` | At least 25,000,000 and less than 40,000,000 ns |
| \`from40to50ms\` | At least 40,000,000 and less than 50,000,000 ns |
| \`ge50ms\` | At least 50,000,000 ns |

Counters are both whole-run totals and per-second buckets. Exact
boundaries use nanoseconds, with no truncation to microseconds until
the *separate* \`max_call_us\` field is exported. A returned exact
descriptor is still only an API/lease event, **not** audible sound.

After joining the audio worker, a second stage-specific exporter uses
the existing exclusive numbered temporary-file/readback/rename
mechanism to publish \`audio-audout-latency-0000.csv\` and independent
\`audio-audout-latency-export-result.txt\` receipt on the guest SD.
Both are distinct from the unchanged proven
\`audio-audout-queue-0000.csv\` format, its filename and receipt.

The CSV schema is:

\`\`\`text
scope,second,attempts,lt25ms,from25to40ms,from40to50ms,ge50ms,failures,max_call_us,overwritten_windows,clock_errors
\`\`\`

One TOTAL line and every surviving SECOND window are included. The
independent verifier rejects time disorder, duplicates, missing seconds,
bad formats, band count inconsistencies, incorrect full-run totals,
clock anomalies, or metadata inconsistent with latency bounds.

The NeXium workflow now captures the **original** new guest SD file,
a separate copy and the writer receipt, and runs
\`tools/audit_nexium_audout_latency.py\` *after* the original
stage-269 queue auditor. Both audits must agree on exact per-call
attempt counts, returned buffers, failures, number of second windows
and overall call-duration maximum. An old queue CSV, newly fabricated
receipt, or missing latency source cannot satisfy this check.

## Proof boundaries

This reports counts of *software API-call durations*. A 50 ms wait
could be expected audio-buffer pacing or host emulator scheduling and
does **not** by itself show starvation or an audible glitch.
\`audoutGetAudioOutBufferCount\` samples still only measure a
pre-submit state. The current workflow does not observe DAC output,
actual device queue continuity, speaker output, physical
Nintendo Switch performance or power-loss durable SD writes.

The Stage 271 baseline comprises completed earlier emulator archives
from an old schema. Their latency-band counts **cannot be retroactively
reconstructed** from per-second maxima. Never backfill zero,
estimate missing counts, or label a synthetic fixture as NeXium.

**Acceptance criterion:** a single actual same-run NeXium workflow
must pass NRO build, optical/SD scene witness, stage-269 original
queue audit and the *new* stage-272 original-SD latency-band audit.
Before that, this stage is implemented but emulator acceptance pending.


## First full NeXium acceptance — run 39069701196

[NeXium workflow run 39069701196](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39069701196) completed both the libnx NRO build and the pinned NeXium audio/optical/SD audit successfully. The same-run NRO at git commit \`57f3d725eaef07666d5b648569055fd75baa4ab1\` had SHA-256 \`86b3b8fe2eef0c30fa25218125de290f2b3078e3c675770f7493f81c1a9edb22\`.

The archived original guest SD file \`audio-audout-latency-0000.csv\` measured **1,942 individual real audout API calls across 53 one-second windows**:

| Nanosecond-qualified duration band | Count |
| --- | ---: |
| Under 25 ms | 741 |
| 25–40 ms | 1,177 |
| 40–50 ms | 22 |
| 50 ms and longer | 2 |
| **Total** | **1,942** |

The two calls at or above 50 ms occurred in guest seconds **37** and **39**. The longest API call lasted **50,545 μs**. All 1,942 descriptors were returned as expected; no audout API-call failures, queue-query failures, dropped windows or reversed guest-clock records were detected. **The occurrence of 50 ms calls is not proof of audible underruns.**

The guest-original latency CSV had length **1,996 bytes**, SHA-256 \`3300dc6dc3edecb2b7a32a4bae98c30dbc871ef96d8f50dd49c12bf7918f5875\`; the independent capture copy matched byte-for-byte. The guest export receipt reported status 0 and matching file size. The original Stage-269 queue CSV was also independently audited, SHA-256 \`74085a04b36faf5c3540fb98d6a5b8247c44980ff2aafaf98fad065eacd5c7fa\`; both audits agreed on 1,942 calls, 53 windows and the 50,545 μs maximum. The optical and guest scene SD CSVs matched for 53 scene events over 61.379 seconds of host virtual PCM.

**Follow-up still pending** for commits after \`57f3d725\`: the auditor now also binds every latency window's attempts, failures and maximum against the independently verified Stage-269 CSV, rather than only comparing whole-run totals. Those stricter checks must pass a newer complete NeXium workflow before being marked accepted. The earlier full workflow remains a valid independent baseline for the old audit.

Nothing about these observations establishes physical Nintendo Switch playback, speaker audibility, end-to-end latency or real audio underruns.
