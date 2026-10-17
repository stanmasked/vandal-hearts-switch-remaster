# Switch Stage 274 — exact timestamped slow audout calls

**Status: accepted in pinned NeXium workflow [39072903722](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072903722) with live original guest SD audit.**
**HARDWARE NOT TESTED. No audible/DAC underrun claims.**

## Motivation and implementation

Previous Stage 273 independently aligned guest scene INPUT events with
*one-second bins* of audout call duration, but did not measure the
time of individual slow calls. Identical-NRO runs recorded their
≥50 ms call in the same guest second as different scene serials (#8
and #7); neither proves a causal relation.

Stage 274 extends only the bounded, owner-thread-only
\`VhAudoutQueueTelemetry\` data structure with 128 chronological slots.
For every call/release operation with
\`end_ns - begin_ns >= 40,000,000\`, the audio thread records the
**absolute guest-monotonic nanosecond begin/end timestamps**, sequential
audout attempt number and exact-descriptor return status. The timestamp
covers the \`audoutPlayBuffer\` call and the synchronous buffer-lease
return handling immediately after it; it is **not** a speaker output
event. Capturing the timestamp doesn't perform heap allocations,
filesystem I/O or synchronization.

If more than 128 slow calls occur, \`slow_dropped\` increments rather
than wrapping, silently overwriting, or misreporting all slow calls as
fully observed. The strict NeXium audit rejects any positive overflow
count. Exact nanosecond durations are retained, not rounded during
classification. All prior Stage 269/272/273 CSV formats remain unchanged.

Only after the audio worker has joined, an *additional* original guest
SD file is staged exclusively, closed, byte-for-byte reread, then
published under a numbered name:

\`\`\`text
audio-audout-slow-0000.csv
audio-audout-slow-export-result.txt
\`\`\`

The versioned CSV schema is:

\`\`\`csv
scope,index,attempt,begin_ns,end_ns,duration_ns,returned,total_slow_calls,dropped_slow_calls
\`\`\`

A TOTAL row contains exact counts and dropped events; each subsequent
CALL row contains the ordinal, 1-based attempt number, actual begin
and end nanoseconds, their exact difference and whether the descriptor
was released successfully.

## Validation chain

\`tools/audit_nexium_audout_slow_calls.py\` is a CI gate following the
Stage 273 original-SD clock/scene correlation gate. It:

1. Reopens the actual isolated guest SD originals for the clock anchor,
   optical scene CSV and slow-call journal, requiring separate identical
   copies, unique filenames and successful producer receipts.
2. Reruns the entire Stage-273 audit and compares its resulting report
   with the previously stored report — no acceptance of arbitrarily
   supplied replacement origins, scene event traces or unrelated
   slow-call sessions.
3. Independently parses the Stage-272 original-verified per-second
   latency histogram, requiring **all** slow calls ≥40 ms, including
   full-session and each-second ≥50 ms classifications, to be accounted
   for in exactly the corresponding guest second.
4. Requires monotonically increasing absolute guest timestamps and
   attempted-buffer serials, each serial inside its own second's
   independently counted attempt interval. Rejects negative, invalid,
   truncated, reordered, extra, overflowed and duplicated evidence.
5. Independently calculates each slow-call's exact before/after or
   overlapping relationship to the ten genuine guest INPUT observations
   at a ±500 ms start-time window. This is **software timestamp ordering**,
   not an inference that a scene switch caused the delay.

Native C and Python regressions deliberately corrupt indices, counts,
durations, originals, receipts and overflow status. Synthetic-fixture
reports **must never** be presented as a real NeXium observation.

## Interpretation boundary

An API call taking ≥40 ms may simply be waiting for an audio buffer in
NeXium. The trace does not prove a dropped playback sample, an audible
pop, hardware queue exhaustion, or a change to the music's actual DAC
output time. It also does not align guest timestamps with the host PCM
clock. Observed temporal ordering is not causality.

A successful full pinned NRO NeXium workflow and original guest SD
capture are required before this stage is marked accepted. If that
run fails, inspect its actual job logs and correct the implementation,
rather than retrospectively inventing slow timestamps from Stage-273
per-second aggregates.


## First archived guest slow-call copy: NeXium run 39072563324

A completed pinned [NeXium run 39072563324](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072563324) at commit
\`86fc583c4c8a70a44ec4d37fda332279beab6fc9\` (NRO SHA-256
\`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb\`)
successfully generated and archived \`soak-audout-slow-unverified.csv\`,
a byte copy from the guest SD path, and its independent writer receipt.

An independent offline audit of **that archived copy**, rather than
a retroactive guess based on Stage 273 one-second maxima, found:

- 1,915 actual \`audoutPlayBuffer\` calls over 53 guest seconds, all
  returned, 0 API return failures;
- 25 individually timestamped calls ≥40 ms, including **3** ≥50 ms,
  with zero overflow/dropped slow-call records;
- 25/25 individual observations agreed with their per-second ≥40/≥50
  bins, per-second maximum duration (truncated to μs), and the
  50,929 μs whole-session maximum;
- Archived slow-call-copy SHA-256:
  \`1eaafd07aec1f23ce06226104d48dbdc53184e4b438e6988973e33cecd7ef033\`.

Actual guest INPUT timestamps permit the following narrow ordering,
using a ±500 ms **slow-call start-time selection** window:

| Guest scene INPUT serial | Observed slow calls near INPUT |
| --- | --- |
| 1 | one 48.615 ms call **began 228.487 ms after** INPUT |
| 6 | 41.644 ms and 44.160 ms calls began **166.517 / 221.820 ms after** |
| 7 | 48.754 ms call **completed before** INPUT |
| 8 | 43.217 ms call **began 0.036 ms before and ended after** INPUT; 42.051 ms call began **157.510 ms after** |
| 10 | 50.930 ms call **completed before** INPUT; 45.207 ms call began **87.367 ms after** |

**Evidence boundary:** The archived guest-SD *copy* and verified
Stage-272 histogram can be compared offline, but this particular
offline reanalysis did not reopen the original transient runner SD
file; it cannot independently certify that original. That stronger
requirement is enforced only by the dedicated Stage-274 GitHub Actions
\`audit_nexium_audout_slow_calls.py\` step on a newly running workflow.
Do not call the archive-copy analysis the final original-SD
acceptance. Also, a programmatic ordering comparison does not
demonstrate scene-switch causality, DAC timing or audible underruns.

The Stage-274 negative-control test previously contained a synthetic
input timestamp at a ±500 ms selection boundary that included an
additional legitimate slow call from an adjacent second. Corrected the
*test-only* timestamp in commit \`aa04c510\`, without modifying runtime
audio scheduling or production audit criteria. Full workflow results
after this correction remain tracked separately.


## Full original-SD acceptance and same-NRO two-run comparison

The complete current-NRO [NeXium workflow 39072903722](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072903722), commit
\`e358f657ddd7b0759098e9adbf7eef30846ca736\`,
successfully passed both **"Verify guest-clock-bound scene input and
audout-second relation"** and **"Verify exact guest slow-call timing
relative to scene INPUT"**. The independent Stage-274 auditor
reopened the original isolated guest SD files *while the workflow
was active*, validated their separately copied versions and writer
receipts, and cross-checked the Stage-269/272/273 evidence. The
host regressions also passed in [run 39072904079](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072904079).
This meets the original acceptance criterion; older archive-copy-only
evidence must still be labeled appropriately.

The validated same-run NRO SHA-256 was
\`4be7635609589952363d3255e81537343a5893bff3611ecd30df48d39d6f35cb\`.
From its original-SD-verified archive:

- **1,942** attempted audout calls, all returned; **53** seconds;
- **20** calls 40–<50 ms and **2** calls ≥50 ms; **22** exact
  start/end timestamp records, **zero** overflow/drops;
- maximum call **53,503 μs**; all 22 timestamps agree with
  the Stage-272 independently audited second-by-second histogram;
- guest-SD original/copy slow-call CSV SHA-256:
  \`4e0dab47f81bd46a7dedb89327e90e34df02fc14f23943fe036c3eddf23a4935\`;
- ten complete music scene INPUT events; within the defined ±500 ms
  **slow-call START** window, calls ≥40 ms appeared near serials
  1, 9 and 10. Each of those calls ended before the respective
  INPUT; *none* of the two ≥50 ms calls began within that ±500 ms
  window around any scene INPUT.

For comparison, completed NeXium [run 39072563324](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39072563324),
commit \`86fc583c\`, used the **identical SHA-256 NRO** and produced
1,915 calls across 53 seconds. Its separately archived slow CSV had
25 exact ≥40 ms records including 3 ≥50 ms calls, zero overflow,
with 50,929 μs maximum. Offline byte inspection independently checked
that the archive copy and the prior Stage-272 per-second histogram
agreed. However that older workflow **did not execute the separate
Stage-274 original-SD slow-call audit**, so it is copy-audited only,
not an additional live original-SD acceptance.

The two identical-NRO runs therefore observed:

| Measure | 39072563324 (copy only) | 39072903722 (original-SD audited) |
| --- | ---: | ---: |
| Audout attempts | 1,915 | 1,942 |
| Calls 40–<50 ms | 22 | 20 |
| Calls ≥50 ms | 3 | 2 |
| Slow-call records lost | 0 | 0 |
| Maximum call, μs | 50,929 | 53,503 |
| ≥50 ms calls whose start was ±500 ms of scene INPUT | 1 (serial 10) | 0 |

The earlier ≥50 ms call ended 0.462 ms before INPUT serial 10.
There is **no reproducible association of ≥50 ms calls with the
same scene transition** across these two runs. This does not prove
absence of scene-related scheduling effects, real device underruns
or audible playback issues. The latest archive comparison **cannot**
reopen the runner's now-ephemeral original guest SD; that stronger
claim is based solely on the separately observed successful workflow
step, not on retrospective archival inference.

Current follow-up: compare two or more future fully original-SD
accepted Stage-274 archives from the same NRO with the same rules.
