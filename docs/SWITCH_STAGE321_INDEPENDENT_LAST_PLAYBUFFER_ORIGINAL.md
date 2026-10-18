# Vandal Hearts Remake — Stage321: independent original last PlayBuffer source replay

## Evidence question

Stage317 and the independent Stage318 NeXium audit established the
guest software order:

1. Game loop requested audio stop.
2. The last normal audout PCM buffer lease was returned.
3. The worker observed its mailbox running flag become false.
4. The worker entered audio cleanup.

The original Stage318 source replay measured 11.942917 ms between
the main stop request and the last returned normal PCM page, then
0.126666 ms until worker stop observation and 0.106459 ms until
cleanup. These are **guest software monotonic** time intervals,
not sound on hardware.

Stage320 adds a new source-original CSV with the already measured
begin/end times of the **last successful audoutPlayBuffer call**. It
does not request another guest clock in the output hot loop. This
lets us measure both service-call duration and the amount of the
last call *after* the stop request, without assuming that the whole
11.94 ms interval belongs to one call.

## Stage321 independent source replay

`tools/replay_nexium_original_last_playbuffer_archive.py` on a
separate GitHub Actions runner requires the original Stage320
NeXium source workflow **39154247222** to have *completed
successfully*. If the producer remains queued, fails, is cancelled,
or did not publish the original source files, Stage321 does **not**
report a verified measurement.

The script requires these original guest-created files in the same
archived runtime evidence directory:

- `audio-exit-timeline-000.csv` (guest Plus/stop/cleanup/close/join)
- `audio-exit-output-000.csv` (last successfully returned PCM page)
- `audio-exit-worker-stop-000.csv` (mailbox running flag observed false)
- `audio-last-playbuffer-000.csv` (last successful service begin/end)
- `scene-optical-trace.png` (original CRC-protected guest scene source)

It also requires source-bound Stage307/308/310/313/314/317/320 JSON
receipts. The earlier raw CSVs and optical PNG are independently
replayed via the Stage318 source audit, and the Stage320 original
CSV is independently parsed and rehashed. The Stage320 capture-time
receipt must reproduce **exactly** from the original bytes.

The generated report includes:

- Duration of last successful PlayBuffer call on the guest clock.
- Portion of that call following the guest stop request, if any.
- Guest time between service return and the later owner-side
  last-buffer witness.
- Whether the call finished before, straddled, or began after
  the stop request.
- SHA-256 hashes of the original PlayBuffer, exit, worker stop,
  last-page, and optical source files.

**Thirteen adversarial synthetic tests** verify exact replays,
source tampering, forged receipts, swapped optical images, missing,
duplicated, symlinked and separated original sources, and strict
non-audible evidence flags. They run under both Host SPU and the
independent original-capture replay workflow.

## Interpretation limits

An `audoutPlayBuffer` return is a successful buffer-lease
observation. The bracket timestamps are guest software measurements,
not the end of playback on the real Nintendo Switch DAC, the last
audible speaker sample, or a measured host PulseAudio PCM frame.
One call cannot automatically be credited with the *entire*
stop-request-to-cleanup delay. No PlayStation retail music assets,
SPU synthesis, queue scheduling, shutdown control or gameplay
behavior are changed by Stage321.
