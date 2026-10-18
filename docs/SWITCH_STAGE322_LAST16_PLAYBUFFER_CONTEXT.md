# Vandal Hearts Remake — Stage322: context for the last audoutPlayBuffer call

## Verified motivation

The real Stage320 NeXium run
[39154247222](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39154247222)
and separate Stage321 source replay
[39156088373](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39156088373)
both succeeded.

The last successful normal `audoutPlayBuffer` call lasted **28,391,093 ns**
(28.391 ms) on the **guest software clock**. Of this, **27,834,739 ns**
fell after the game loop requested music stop. Another **2,709 ns**
elapsed between the call's return and the owner-side normal PCM
buffer release witness. The Stage321 independently reaudited
original-source partition exactly conserved these intervals.

These values show that the last **one** call overlapped most of
that run's guest stop-to-page interval. They do **not** show whether
this call was unusual during ordinary music playback, or that an
audible defect occurred. The earlier Stage317 capture measured a
different shutdown and must not be treated as the same run.

## New fixed-capacity guest witness

`source/vh_audio_playbuffer_history.h` retains the last **16
actual normal PlayBuffer service attempts** in a fixed C array.
Every row records its monotonic sequence number, original guest
software begin/end timestamps, and whether the *exact buffer
descriptor lease* returned successfully.

This records no raw PCM, game audio assets, retail soundtrack, or
speaker output. Memory is bounded to 16 entries regardless of the
length of the game session. Stage322 uses Stage320's **same existing
begin/end clock readings**, makes no extra clock calls, and does
not introduce a new service call, wait, mutex, heap allocation or
filesystem I/O in the audio path. It does introduce one small
bounded in-memory diagnostic record per call; it is not described
as zero CPU overhead.

After audio-worker join, the original guest file is exported via
exclusive creation to:

`sdmc:/switch/vandal-hearts-remake/audio-playbuffer-history-000.csv`

A wrapped history lists precisely the last 16 actual service-call
attempts. The total original call count is repeated in each row,
allowing a separate auditor to verify that rows and sequence
numbers were not omitted, duplicated or reordered.

## Authentic-source audit

`tools/audit_nexium_guest_playbuffer_history.py` reads the
original isolated guest SD root, independently re-audits the
source-bound Stage320 last successful PlayBuffer bracket, and
checks the new original history CSV:

- canonical header, bounded size and exact row count;
- every sequence is consecutive and its timestamp pair is
  monotonic relative to the preceding retained call;
- original retained success/failure statuses cannot contradict
  Stage320's global service-call counters;
- the last retained successful call agrees with the original
  Stage320 begin/end time, duration and successful attempt index;
- invalid clocks, missing source, symlinked input, duplicate
  numbered sources or contradictory receipts fail closed.

The result includes each actual recent software-call duration and,
only if the final successful call and earlier successful calls
are present in the bounded window, the minimum, lower median,
maximum and final-minus-earlier-median intervals. It explicitly
reports no prior baseline when none can be proven. A missing
final success from the retained 16 is also marked, never invented.

The authentic NeXium job preserves the original bytes and
SHA-256 in `runtime-evidence/audio-playbuffer-history-000.csv`,
with derived report
`runtime-evidence/guest-playbuffer-history-stage322.json`.

## Tests and evidence limits

- Native C11 GCC/Clang tests for wrapped 16-entry order, failed
  service-call status, invalid clock rejection and empty-source
  non-fabrication.
- 14 Python source mutation and partial-history tests.
- Host SPU / Makefile and full libnx NeXium smoke integration.

All timings are **guest software service** brackets. Neither a
buffer-lease return nor its duration locates the final sample at a
DAC, speaker, virtual host PCM file, or any original PlayStation
soundtrack. This is diagnostic instrumentation, not a game
playback change or a causal assertion about the Plus key.
