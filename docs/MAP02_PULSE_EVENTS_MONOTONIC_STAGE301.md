# MAP02 Stage301 — independent real PulseAudio notification receipt clock

Research-only stacked child of [Stage300 PR #383](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/383). **Draft / DO NOT MERGE.** No original-game ROM, original PS1 music, production NRO/game source, NeXium upstream, `main` or CPAL callbacks modified.

## The limitation established in Stage300

[Stage300 successful source-only retrospective Actions #39513669874](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39513669874) independently validated the original Stage299 Pulse sink-input snapshots from both genuine guest runs. On 21ms, the stereo 48k Pulse sink input retained `#2`, and a 32-channel/384kHz input retained `#94`, both uncorked despite no new CPAL callbacks. On 22ms, stereo 48k sink input changed `#2 -> #14` while 32ch/384k retained `#11`; the generated research NRO passed 8/8 CRC and 492050 nonzero virtual PCM samples. Snapshot IDs could not tell WHEN a Pulse notification arrived or whether the observed change had anything to do with CPAL callbacks.

## Stage301 original-source run protocol

Two independent Ubuntu 24.04 guest jobs request Pulse `PULSE_LATENCY_MSEC=21` and `22`. Every job downloads and SHA-verifies the **same** newly built Stage298 research Linux/Rustarmic ELF `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a` (Actions `39509934054`) and the immutable generated-only ROM-free NRO `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b` (Actions `39460035568`).

Only the separate Stage294 *research launcher* is copied. After the existing null Pulse sink is ready and before the untouched GUI/NRO launch, Stage301 subscribes through `pactl subscribe`. A standalone Python watcher writes sanitized `new`, `remove`, `change` notifications **only for Pulse sink-input IDs**, with timestamp from `time.monotonic_ns()` when the watcher **READS** each event from a local IPC pipe. It also writes explicit watcher start/stop markers. A short 500ms opt-in watcher settling interval is added before game launch; it may perturb the guest/audio scheduling relative to previous Stage299, so Stage301 must not be treated as a controlled no-change timing comparison.

The source-identical guest keyboard inputs `c x m` and the old Stage294 screenshots, original 48k virtual PCM and GUI FileLogger are retained. Two Pulse sink-input snapshots are bracketed by separate before/after `time.monotonic_ns()` markers; input and late guest observation retain their independent monotonic markers. Stage298 `P` and untouched `L` report the same exact-sample CPAL stream play/drop and callback counters.

## Falsification and privacy

- Run existing Stage299 tests, Stage300 sink-input tests, plus 11 new event parsing synthetic tests.
- Independent Stage299 raw PNG/optical-CRC, original NRO/ELF SHA, real FileLogger, P/L counter and raw virtual PCM SHA audit on **both** newly executed guests. Do not force a particular guest result: stalled/truncated optical data at 21ms remains a valid observed outcome, not fabricated success.
- Source-pinned Stage301 audit independently cross-checks watcher clock bounds, matching NeXium process in both original Pulse snapshots, Pulse profile+client+sink lineage, new Pulse notification for a replaced sink input, and whether the **receipt timestamp** fell between the bracketing snapshot windows or guest input.
- Subscriber records are sanitized; no original host PID, hostname, username, native Pulse properties or raw GUI logs uploaded. Unmodified existing Pulse snapshots are parsed on the runner but **not** included in the resulting uploaded artifact; SHA-256 digests and sanitized profiles are present in the final Stage301 JSON. Backend CPAL and original 11-field L counters are unchanged.

## Limits

A Pulse `pactl subscribe` notification contains no guaranteed original device event timestamp. Our monotonically stamped receipt is **not** the exact time CPAL created/released/paused a stream and may lag the actual Pulse server event because of pipe latency/scheduling. Seeing `new` for `#14` is not proof that CPAL or ALSA itself recreated/terminated a hardware stream or that the event caused callbacks to resume. `Corked: no` is also not proof that callbacks are alive. These runs do **not** establish a permanent guest deadlock, stable 21/22ms boundary, original PS1 soundtrack fidelity, actual Nintendo Switch DAC/speaker function or production audio fix.
