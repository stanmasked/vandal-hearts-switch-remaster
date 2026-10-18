# Stage 289 — Timestamped pre-submit audout service probes

Prior Stage288 proved alignment of scene INPUT timestamps with slow
`audoutPlayBuffer` software call durations on the SAME guest monotonic
clock in eight historical NeXium source pairs (CI 39086324572).

**There is no independent Nintendo Switch audio scheduler callback
trace** in those historical archives. This new version cannot create
one retrospectively or infer DAC behavior from audout's queue count.

The native audio owner already calls
`audoutGetAudioOutBufferCount` every 16 submitted buffers (Stage269).
Stage289 adds **no new libnx queries, allocations, locks or I/O inside
the worker loop**. When the existing query returns, the existing
`vh_audout_queue_record()` copies a bounded snapshot into 256
owner-thread-only slots containing:

- Sequence attempt index (1, 17, 33, …) on the ordinary successful path;
- Absolute guest `audoutPlayBuffer` **submit-begin timestamp**, stamped
  **AFTER** the service-count query. The exact query timestamp is
  **not** known;
- Whether that service query failed or succeeded; the returned queue
  count only when it succeeded.

A separately bounded dropped-event counter makes overflow explicit.
No new CSV changes the Stage269, 272, 273 or 274 schemas. After the
worker joins, `audio-audout-probe-0000.csv` is saved with exclusive
temporary-file staging, byte-exact readback, an immutable numbered
name and a separate writer/visibility receipt.

The strict independent `tools/audit_nexium_audout_service_probes.py`
refuses an audit unless the **original current-run guest SD file**
and its copied artifact match byte-for-byte, the writer receipt
identifies the same byte count, and all clock-origin, original queue
summary, latency histogram, slow calls and scene input originals
match. It checks that every probe corresponds to the correct
1-in-16 attempt, that its timestamp lies in its actual guest service
second and, if the attempt was ≥40 ms, that its begin timestamp
equals the independently timestamped slow call exactly.

An independent NeXium workflow gate makes missing probe files,
overflow, stale copies, forged status, altered timestamps, NRO/runner
mis-binding and repeated records fail closed. Native C tests also
verify bounded memory, overflow, canonical writer/readback and
exclusive non-overwrite publication. A probe can **never** establish
when an already-queued buffer reaches the DAC or whether the guest
OS scheduler blocked an unrelated thread.

The actual signal delivered is **pre-submit service buffer-count
observation at a subset of calls**, not an OS scheduler state
witness. Any finding of relationship to music INPUT or slow calls
remains **software temporal co-occurrence only**. A distinct
instrumented scheduler callback would be needed for more.
