# Stage362 — recorder-stop host monotonic clock alongside strict legacy wall epoch

## Motivation

Authenticated [original NeXium #39333759265](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39333759265) passed Stage351/357/360 original guest-source checks but the **overall run failed** at strict Stage303: the host `scene-recorder-stop.csv` recorded wall epochs `1792449461974` then `1792449461203` ms, a **-771 ms** regression. The two buffered host PCM file-size readings were both `8732688` bytes. Nothing in that old source establishes whether the Linux host's monotonic clock also advanced between the stop observations, so wall-clock resynchronization/jumps cannot yet be distinguished from capture chronology defects. Neither possibility proves a guest audio fault.

## New capture and independent audit

For **future** full NeXium guest captures only, `tools/capture_nexium_scene_audio.sh` now samples `time.time_ns()` and `time.monotonic_ns()` together inside one host Python invocation for each existing recorder stop observation (before SIGINT and after recorder wait). The original `scene-recorder-stop.csv` columns remain exactly `event,pcm_bytes,host_epoch_ms,signal_success`; it is neither removed nor reinterpreted. A new `scene-recorder-stop-monotonic.csv` companion contains the *identical* old fields plus `host_monotonic_ns`. These clocks are host-side observations, not guest media or system-on-chip/DAC clocks, and they are not sampled atomically with PCM output.

The independent Stage362 Python audit requires the two CSVs to have exactly two canonical ASCII rows in the right order with byte-identical old field values and a *strictly increasing* new host monotonic timestamp. It reports separate signed wall and monotonic deltas. When wall time decreases, it explicitly reports `host_wall_clock_moved_backwards=true` and `strict_stage303_chronology_compatible=false`. The original strict Stage303 script is unchanged and retains its fail-closed behavior.

In `.github/workflows/emulator-smoke.yml`, Stage362 is placed **after** the original strict Stage303 step and uses `if: always() && steps.scene_capture.outcome == 'success'`, so its explanatory report can still be captured if Stage303 fails. The independent regression workflow `.github/workflows/stage362-recorder-stop-dual-clock.yml` tests forged timestamps, changed byte counts, bad event sequences, malformed numeric fields, non-increasing monotonic timestamps and symlink rejection. These unit tests use **synthetic** clocks and cannot claim a new real NeXium observation.

## Evidentiary limits

- Stage362 does not modify the emulated audio engine, guest `audout` calls, PCM samples, the 48-kHz playback path, 96-frame tail, buffer lease policy or the single 12-ms wait.
- A monotonic-positive host pair does not by itself make the original strict Stage303 pass: the original wall timestamps may still move backwards and must remain invalid.
- Old NeXium #39333759265 **does not have** a recorder-stop monotonic companion. It cannot be retroactively repaired or used as if it had one.
- No inference about game audio hardware, scheduler timing, speaker output, audible dropouts, or why the Linux wall clock regressed can be made from the old recording.
- Real Stage362 paired recorder-stop values must come from a **new actual NeXium run**, not the synthetic CI tests.
