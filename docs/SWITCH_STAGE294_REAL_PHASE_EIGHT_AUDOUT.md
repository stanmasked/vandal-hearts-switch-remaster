# Vandal Hearts Remake — Stage294: experimentally shift the real audout queue query phase

Stages 291–293 established that querying pre-submit audout service
queue count on every **16th** call at **phase0** misses many software
call durations ≥40ms observed independently at the other 15 phases.
This does NOT mean their queue service counts are nonzero: those
counts were never requested. Phase selection must be tested with
**a genuinely different guest NRO**, rather than imputation.

## New bounded guest control

The phase resides in owner-thread telemetry and may be set only
before the first audout submission; default 0 is unchanged.
Invalid phase <0 or >=16 is refused at compile-time; the
runtime setter rejects all values outside 0–15, and rejects changes
after the first attempted submission or service observation.
The only hot-path change is a comparison of call index modulo
16 to a constant phase. The number of service queries remains
at most one in every 16 submitted audout calls, and the query
is still issued immediately BEFORE `audoutPlayBuffer`.

The existing baseline NRO still queries attempts **1,17,33,...**
and retains all historical CSV schema/CI acceptance rules.
A distinct experimental phase8 NRO queries attempts
**9,25,41,...** and lives in a **separate build directory**.

## Real NeXium experiment and source authentication

The same workflow builds both NROs with per-file SHA-256
manifests bound to current Git commit, GitHub workflow run
and attempt. A distinct guest SD root for phase8 ensures
no baseline source files can be accidentally substituted.

The phase8 NRO performs the actual NeXium scene-switch capture,
writes its own genuine pre-submit queue samples and original
guest-SD export receipt; the strict independent phase-aware
auditor checks the ORIGINAL guest file against the copied
artifact, clock anchor, complete latency bands, exact ≥40ms
call timestamps, scene INPUTs, attempt indices (9+16k),
service queue minima/maxima, source receipts and overflow.

This phase8 run occurs AFTER the existing phase0/idle/16-call
workflow and does not replace its independently validated
source records. Two guest NROs collected sequentially are
**not** a simultaneous, randomized causal experiment:
time-varying host scheduling and recording conditions may
also change. An observed queue count is a pre-submit service
snapshot, NOT guest OS scheduler state, DAC starvation,
physical Switch audio or audible music correctness.
