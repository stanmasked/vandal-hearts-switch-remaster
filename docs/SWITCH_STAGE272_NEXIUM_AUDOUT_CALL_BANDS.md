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
