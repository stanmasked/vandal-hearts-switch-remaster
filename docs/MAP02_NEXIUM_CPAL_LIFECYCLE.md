# MAP02 Stage286 — CPAL stream lifecycle instrumentation (research build only)

**Draft / DO NOT MERGE.** Parent: [Stage285 PR #335](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/335), frozen at `1870f825c4443502825353135906af66e1e45361`. No original game ROM, original game audio, Nintendo Switch production source, or existing compiled NeXium binary is changed.

## Why a new probe is needed

Six original guest runs were independently rechecked in [Stage284 Actions #39481359555](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39481359555). [Stage285 Actions #39486131186](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39486131186) then re-parsed their exact raw CPAL timestamps: all three requested 21-ms cases had **0 CPAL callback entries after game input**, whereas three 22-ms runs recorded **2243, 2242 and 2242 entries**. However, Stage274's ~200-ms reporter could not say whether the stream was lost, paused, reported an error, or simply stopped receiving Linux/Pulse callbacks.

## Exactly what Stage286 changes

A new fail-closed overlay applies **after** the previously verified Stage274 CPAL/AudioOut source patch, to the immutable upstream `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219`. The new change is confined to `nexium-runner/src/audio.rs`:

- Tracks entry into stream initialization, missing default device, stream configuration failure, build attempts, build success/failure and successful/failed `stream.play()`.
- Increments a single **relaxed atomic counter** when the real CPAL error callback fires. There is **no additional allocation, filesystem write, monotonic-clock syscall, mutex or sleep introduced into that callback**. The existing original error logger is left in place.
- Uses an experimental Linux thread-local wrapper holding the actual CPAL stream so its `Drop` callback records how often the stream is disposed. Other targets use the original underlying `cpal::Stream` type.
- Records monotonic CLOCK_MONOTONIC timestamps for stream *build attempt*, successful *play* and *drop*, only on their non-audio-callback code paths.
- A separate opt-in reporter enabled by **absolute** `VH_MAP02_CPAL_LIFECYCLE_PATH` samples the above counters and recorded event timestamps every 200 ms for a maximum of 240 snapshots. It writes from its own non-real-time thread. The original Stage274 `VH_MAP02_CPAL_TRACE_PATH` CSV and guest AudioOut counters **remain unchanged**.

New reporter columns are `L,monotonic_ns,init,device_missing,config_failed,build_attempt,build_failed,build_ok,play_failed,play_ok,error_callback,stream_dropped,build_start_ns,play_ok_ns,drop_ns`.

The new error callback increment is atomic, but its *time* is only bounded by the reporter's snapshot intervals. **It is not an exact error callback timestamp.** Silence without a reported error would not identify why Linux/CPAL stopped invoking the callback. The wrapper observes `Drop`, not every possible explicit CPAL `pause` call elsewhere in the emulator.

## Build gates and separation from real runtime evidence

The isolated workflow `map02-nexium-cpal-lifecycle-check.yml` checks out exact research source and immutable NeXium with its original pinned `rustarmic` submodule, runs the previously accepted Stage274 synthetic tests and 11 Stage286 ROM-free source tests, applies both overlays, validates exact source paths and SHA-256 between stages, runs real Rust formatting/parsing checks, and compiles with:

`cargo check --locked -p nexium-runner --no-default-features --features backend-rustarmic`

The dependency lock must equal the independently established Stage275 Cargo.lock SHA-256 `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`.

**This stage prepares and type-checks an experimental source overlay only.** Even a green CI does **not** produce or execute a new ELF, observe an actual CPAL lifecycle event, rerun the guest, test the original PS1 soundtrack or demonstrate physical Nintendo Switch DAC audio. The prior six-trial ELF SHA-256 remains the historical baseline and is deliberately not overwritten.

The next stage, after a successful type-check, is a separate release build with an independent new ELF SHA, then a controlled guest replay enabling *both* reporter paths. Because adding the reporter itself changes runtime scheduling, its 21/22-ms results must be compared carefully against the untouched six-run control, without declaring any difference a production audio repair.

**No automatic merge.**
