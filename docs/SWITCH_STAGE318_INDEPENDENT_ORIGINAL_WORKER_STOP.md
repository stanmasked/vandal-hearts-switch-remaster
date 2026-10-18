# Vandal Hearts Remake — Stage318: independently replay the ORIGINAL guest stop-observed marker

## Motivation

Stage316 successfully cross-validated two independent NeXium software
last-buffer-return witnesses: the last ordinary PCM audout page
returned **23.212605 ms** after the game loop observed Plus in the
first run and **18.693125 ms** in the next run. In both cases,
buffer ownership returned after the main thread requested music stop
but before the audio worker entered cleanup. Buffer *return* does
not establish physical sound or the moment the worker observed stop.

Stage317 introduces a one-shot **guest software** marker at the
existing audio-worker running-flag read, and exports the original
guest-created `audio-exit-worker-stop-000.csv` after joining.
The original five-row Stage307 exit and Stage313 last-page CSVs are
not changed.

## Independent archive replay

The standalone GitHub Actions workflow
`.github/workflows/stage318-independent-original-worker-stop.yml`
runs on a separate machine after the *exact original Stage317*
NeXium capture workflow **39150385701** has completed successfully.
It fails if the original run fails, the guest SD bytes were not
published, or the artifact download is absent. Partial capture is
never accepted as a valid source.

The auditor
`tools/replay_nexium_original_worker_stop_archive.py` requires the
following **original** evidence from one runtime artifact directory:

1. `audio-exit-timeline-000.csv` (guest-created Plus/stop/cleanup/close/join)
2. `audio-exit-output-000.csv` (guest-created last normal PCM page return)
3. `audio-exit-worker-stop-000.csv` (new guest-created observation of stop)
4. `scene-optical-trace.png` (original CRC-protected music-scene optical trace)
5. Original Stage307, Stage308, Stage310, Stage313, Stage314 and Stage317
   source-bound JSON receipts.

It refuses missing, duplicate, symlinked, separated or oversized
original guest source inputs, and does **not** reconstruct a CSV from
any report. It independently parses all three original CSVs,
recalculates their SHA-256 hashes, checks the guest optical packet CRC,
and reproduces the exact prior diagnostic receipts.

Stage318 independently requires:

`stop requested <= last normal audout buffer return <= worker observed stop <= worker cleanup entered < audout closed < joined`

When both guest sources and the new worker marker pass, it publishes
three ordered guest software intervals:

- stop request → last normal PCM buffer *lease return*
- last normal PCM buffer *lease return* → worker observed stop
- worker observed stop → worker entered cleanup

This helps distinguish a previously blocking `audout` call from a
worker that already observed the cooperative stop flag. It is not a
DAC or speaker latency measurement.

## CI and scope

- 14 synthetic adversarial original-source fixtures; also executed in
  Host SPU CI.
- Separate original-run-dependent workflow uploads only its newly
  regenerated Stage318 JSON report. No PCM, retail soundtrack,
  firmware, keys or game image files are published by this addition.
- Audio worker playback logic, PCM synthesis, exit taper, sound asset
  loading, output buffers and gameplay inputs are unchanged.

The guest monotonic nanosecond timestamp is **not** calibrated to
host PulseAudio buffered PCM samples, hardware DAC timing or an
audible original PS1 soundtrack. No Plus-caused audible dropout
or physical Switch sound has been established.
