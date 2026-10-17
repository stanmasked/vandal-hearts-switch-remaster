# Switch Stage 274 — exact timestamped slow audout calls

**Status: acceptance pending a full pinned NeXium workflow with the new CSV.**
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
