# Vandal Hearts Remake — Stage 273: Guest-clock audout / scene co-occurrence

**HARDWARE NOT TESTED.** This diagnostic relates two distinct **guest**
software observations on the same monotonic clock. It does not determine
audible quality, device queue starvation, end-to-end input latency, or a
causal effect of scene switching on \`audoutPlayBuffer()\`.

## Why this stage needs a new on-guest witness

Existing \`audio-audout-latency-0000.csv\` seconds are **relative to
the time of the first audout API call** (\`origin_ns\`). The game
\`audio-scene-trace-0000.csv\` INPUT/POST/ACCEPT timestamps are **absolute
guest monotonic nanoseconds**, from the same \`armTicksToNs(armGetSystemTick())\`
source. Those cannot be aligned precisely from old Stage-272 archives
because \`origin_ns\` was not exported. Do not infer it from a host
\`soak-events.csv\` file or a scene's first visible framebuffer.

This stage captures that missing point **from the actual audio worker's
telemetry**, after joining the worker. An independent exclusive numbered
original guest SD file \`audio-audout-clock-0000.csv\` contains:

\`\`\`csv
schema,origin_ns,attempts,last_second,clock_errors
vh-audout-guest-clock-origin/v1,<guest ns>,<whole-run call count>,<last second>,0
\`\`\`

This is byte-exact read-back verified via an exclusively created temporary
file and rename; it does not alter the successful previous audout queue
or latency CSV schema. A separate
\`audio-audout-clock-export-result.txt\` receipt records success, path
visibility and exact size. Both are copied to the NeXium artifacts;
the audit checks the **original** isolated guest SD file too.

## Accepted evidence and exact interpretation

\`tools/audit_nexium_audout_scene_correlation.py\` requires original and
copied guest clock bytes, a valid clock-export receipt, the previously
verified Stage-269 queue report, Stage-272 per-call latency report and CSV,
Stage-268 optical/guest-SD scene report and corresponding original scene
trace on the isolated SD.

For each of exactly ten traced INPUT serials, the guest audio second is:

\`\`\`text
second = floor((input_monotonic_ns - first_audout_call_origin_ns) / 1_000_000_000)
\`\`\`

That second must be within the 50+ measured guest latency windows.
The resulting report includes each serial, scene, absolute guest time,
second index, offset within the second, number of actual calls ≥40 ms and
≥50 ms **in that second**, plus descriptive counts for adjacent seconds.

This is a **one-second co-occurrence** measurement only. It cannot say
whether a particular slow call happened before or after a scene INPUT
inside that window. The adjacent-second values are context, not evidence
that a slow call was triggered by the transition. Physical audio
monitoring and host PCM markers are intentionally excluded from the
guest clock alignment claim.

Fail-closed negative controls cover: wrong guest origin, duplicate/odd
clock rows, scene serial/order/guest timestamps, elapsed events outside
the audout capture, changed original SD file, altered optical/SD scene,
writer receipt errors and mismatched source audits. The stage-272
audout-bin verifier additionally checks every second against the
original audout queue CSV, so forged per-second counts cannot be
concealed by matching whole-session totals.

## Distinguishing old and new evidence

Historical successful Stage-272 run
[39069701196](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39069701196)
contains 1,942 individually timed API calls, including 2 at/above
50 ms in seconds 37 and 39, but **has no clock-origin witness**.
It cannot be used to claim that either slow call occurred near a
specific scene transition. Correlation claims must come from a new
post-stage-273 full NeXium run and its preserved original SD files.

The validation gate is in
\`.github/workflows/emulator-smoke.yml\`. Passing host-only synthetic
tests is necessary for regression coverage, but is not a substitute
for a live guest capture. Until that gate passes, the new clock-origin
correlation is **implemented but not yet accepted in NeXium**.
