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

The exported audio origin must ALSO fall between the guest's
startup `SUBMIT_CALL` and `RELEASE_RETURN` timestamps (serial 0)
from the independently verified optical/SD scene trace. This
independently brackets the very first API invocation; merely
substituting an arbitrary absolute timestamp cannot satisfy the audit.

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


## First real NeXium guest-clock observation — run 39070903030

The complete pinned NeXium [Actions run 39070903030](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39070903030), at commit
\`909ea9a024f95c660c5f84e8667b30482b9572ed\`, succeeded.
The current-run build NRO SHA-256 was
\`8b18fbac476500ec7725a71cc974039d5947c36ec5eebd33d982ea66c6ab8601\`.
The real original guest SD clock CSV (independently matched to its copy)
contains \`origin_ns=104954218\`, 1,941 audout calls and 53 windows.
The verified optical scene events independently bracket that origin:
startup \`SUBMIT_CALL\` at 101,590,625 ns, guest audio origin at
104,954,218 ns, and \`RELEASE_RETURN\` at 145,698,645 ns.

Validated guest per-call latency counts:

| Call duration band | Calls |
| --- | ---: |
| <25 ms | 722 |
| 25–<40 ms | 1,199 |
| 40–<50 ms | 19 |
| ≥50 ms | 1 |
| **Total** | **1,941** |

The longest measured call lasted 50,481 μs. All 1,941 buffers were
released without audout errors. Host virtual PCM capture lasted 61.397
seconds and ten guest scene transitions were confirmed.

The ten guest INPUT events correlate with audio second-window indexes
**5, 10, 15, 19, 24, 29, 33, 38, 43, 47**. Their corresponding
same-second count of calls lasting at least 40 ms was
**0, 0, 1, 0, 0, 1, 0, 1, 0, 1**, respectively. The **only** call
≥50 ms fell in second **38**, which also contains guest INPUT serial
**8**. Its specific time or causal relation to the scene switch
is **not measured**. One-second overlap is not input-to-DAC latency.

The original guest SD latency CSV SHA-256 was
\`67ec75e9b34b2c9a27a3474b36dba525f08c50a2a96f4a31f66f86f551e52e11\`,
and clock-origin CSV SHA-256 was
\`dc348b8f265c029015a4ac23adbef56f4b1930fa3f69c769f08029907d6b9c9a\`.
The original CI preserved the verified temporal JSON as
\`runtime-evidence/scene-soak/soak-audout-scene-correlation.json\`
in the \`nexium-runtime-evidence\` artifact.

**Acceptance scope:** the original run passed the stage-273 clock
correlator. A further test committed afterwards added a stricter
synthetic negative control explicitly checking the origin inside the
startup SUBMIT_CALL/RELEASE_RETURN interval. The archival run was
also manually checked against that stricter condition; a new full
CI run after that commit is separately tracked. The older run's
results must not be misrepresented as automatically exercising
subsequently added code.


## Strict origin-bracketing NeXium acceptance — run 39071100764

The second complete [NeXium run 39071100764](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39071100764), commit
\`5defe65ab4d6574f78591225acc8dfd40444dd38\`, **also passed**.
It exercised the extra startup submit/return origin-bracketing
condition, which the previous run did not execute as code. The
NRO SHA-256 remained **identical**:
\`8b18fbac476500ec7725a71cc974039d5947c36ec5eebd33d982ea66c6ab8601\`.

Its real guest clock origin was 132,230,677 ns, independently
bracketed by startup guest \`SUBMIT_CALL\` at 128,161,979 ns
and \`RELEASE_RETURN\` at 173,331,197 ns.
The scene/latency original SD copies passed all audout and optical
checks: 2,011 successful page returns, 53 one-second windows,
zero failed returns and ten transitions over 61.080 seconds of
host-monitored virtual PCM.

One \`audoutPlayBuffer\` call took at least 50 ms, in audio-second
**33**, which also contained INPUT serial **7** (first run: audio-second
38, INPUT serial 8). Thus **the same scene-input serial did not
reproduce** across the two identical-NRO emulator runs. This is
descriptive evidence about host/guest scheduling variability, not proof
that scene transitions cannot affect real hardware audio.

The actual same-second counts ≥40 ms at the ten guest INPUT serials
were **0, 1, 1, 0, 0, 0, 1, 2, 0, 0**. The serial-7
≥50 ms overlap is one-second co-occurrence only, and neither run
supplies the precise timestamp of the individual slow call.

All data above come from the separately archived original NeXium
workflow evidence and are not synthetic-fixture values.
