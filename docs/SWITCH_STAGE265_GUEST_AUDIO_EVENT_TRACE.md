# Stage 265 — bounded guest-origin scene/audio event trace

**Status:** portable recorder and native NRO compiled; emulator guest-log transport is independently checked later. Hardware remains **HARDWARE NOT TESTED**.

## Goal and what is actually observed

The previous NeXium A/B tests showed host-relative detection of synthetic `MUSIC FIELD` and `MUSIC FOCUS` changes, but `parec` file sizes are buffered on the host. Stage 265 adds event markers in the **guest ARM64 application** using one monotonic time domain (`armTicksToNs(armGetSystemTick())`).

The new trace differentiates:

| Event | Point of observation | Critical limitation |
| --- | --- | --- |
| `INPUT` | Main thread sees A/B before applying game rules, but recorded only when scene changes | Not the physical keypress or HID-driver timestamp |
| `POST` | Game thread immediately before updating last-request-wins music mailbox | Not an audio-thread acceptance |
| `ACCEPT` | Audio owner receives success from `vh_music_scene_request` | Cue scheduled, not necessarily audible |
| `SUBMIT_CALL` | Audio owner enters first `vh_audio_output_submit_recover` after cue acceptance | Can block; not proof a DAC received audio |
| `RELEASE_RETURN` | First successful return from submit/recover path | Returned lease/page confirmed; **not** the host speaker playback instant |
| `SUBMIT_ERROR` | Submit/recover failed rather than returned success | Original error handling still fails closed |

Each trace event stores a monotonic guest ns reading and a request serial. The game thread increments serial on each changed music scene, and the audio thread uses two stable atomic ticket reads bracketing the mailbox read. If the scene and serial cannot be matched safely, serial **0** is used; serial 0 must not be interpreted as a specific button press. Simultaneous producer row indices indicate **atomic reservation order**, not necessarily timestamp order.

## Runtime and safety

- Portable trace implementation: `source/vh_audio_scene_trace.[ch]`, exactly **64** fixed slots. Two producers use atomic reservation and release publication, no allocations, mutexes, blocking waits or filesystem calls in the audio render/submit path. Overflow increments `dropped`; old published rows are **never overwritten**.
- Instrumented source: `source/main.c`, `source/vh_switch_game_audio.[ch]`. The main loop samples its own input event time before applying the game state; audio worker emits scene acceptance and first page submit/return events. One audio page event pair is captured per accepted cue; this is **not** a per-page continuous xrun monitor.
- Output is formatted as `VH_AUDIO_SCENE_TRACE_BEGIN` / canonical CSV / `VH_AUDIO_SCENE_TRACE_END` through guest `stderr` **only after `vh_switch_game_audio_stop()` has joined**. Emulators may not bridge guest stderr to host logs.
- `tools/audit_switch_guest_scene_trace.py` strictly audits row count, event type, serial/scene stability, event-clock ordering and event-to-return intervals. `GUEST_TRACE_NOT_OBSERVED` explicitly means transport unavailable or clean guest exit not observed; it is **never** a successful measurement.
- `tests/test_vh_audio_scene_trace.c` tests simultaneous writers, capacity/overflow, atomic-ready snapshots and CSV. `tests/test_audit_switch_guest_scene_trace.py` covers valid/invalid traces, wrong event ordering, malformed CSV and negative controls.
- The host auditor calculates *internal guest-observed* intervals only on complete serials and explicitly sets `hardware_input_to_audio_latency_ms:null` and `dac_output_timestamp_confirmed:false`.

## Compiled native candidate (actually verified)

- [Native integrated NRO build run 39048418666](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39048418666), source SHA `b55746adeff67edb352eb5ba969032e9f1762c64`: **SUCCESS**.
- GitHub artifact `12106314855`: `vandal-hearts-tactical-with-native-music`, ZIP 114,741 bytes, ZIP SHA-256 `17158dc60765429b1014dce12bd02502f3c5a5cafd530158a759d3a4831313d1`.
- NRO exactly **270,392 bytes**, independent download/extraction SHA-256 `3b6b704c7528c3bbc74b46a0b2d2355bc09743fa68cd18a3631f0f12e0f5d173`. ZIP CRC passed and two members were present (NRO + its native SHA receipt).
- CI primary job verifies NRO0 three bounded segments and the new portable C event-trace test.

A subsequent CI run `39048634327` on commit `f28bcdf13aaf771c8519a5d3a96552a53741a07e` **failed** at a *wrong-column negative test fixture* before the build step. The fixture was fixed in `fce1009c1921b813d9572603efe0c2a4a5ba3ff1`, and the corresponding Host SPU, Native PCM and toolchain checks completed **SUCCESS**. The compiled guest source from the earlier build was unchanged; don't cite the failed later NRO run as green.

## Emulator continuation

`.github/workflows/emulator-smoke.yml` was updated to download the exact `39048418666` artifact, verify the new SHA-256, perform the established framebuffer and A/B music tests, and run the guest-trace auditor on the NeXium scene log. `tools/capture_nexium_scene_audio.sh` now requests Plus at the end of the fifth scene to attempt a clean guest exit/trace emission. Whether NeXium actually propagates `stderr` must be read from the new artifact; an absent trace is `GUEST_TRACE_NOT_OBSERVED` (not 0-ms input-to-audio latency).

**Never upgrade to hardware acceptance** from guest-side events. Even a fully matched `INPUT→POST→ACCEPT→SUBMIT_CALL→RELEASE_RETURN` only establishes timing of observed internal operations. Actual DAC output, hardware buffer underruns, SD persistence, HOME/sleep and real sound remain **HARDWARE NOT TESTED**.

## Actual NeXium results and identified evidence-transport blocker

The current emulator workflow [39048953030](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39048953030) on workflow SHA `c93fdbf5a2c7010630e83eaa38c2368c68d4d79e` **completed SUCCESS** (build/test job and emulator job). Its guest binary was the separately pinned and hash-checked NRO from integrated build `39048418666`, not a hidden ad-hoc replacement.

The original [NeXium runtime evidence artifact `12107261023`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39048953030) was downloaded and checked independently. All **34 ZIP members passed CRC**. The archived scene-audio report records 42.661 s of 48-kHz stereo PCM, raw PCM SHA-256 `5d96d1d810c9d6b644e918b313eb7e3ac2a265035cb60296ee0147381a08d52f`, five non-silent intervals, median FIELD zero-crossings proxy **307.614 Hz**, median FOCUS **526.652 Hz** (ratio 1.7121), and `REPEATED_SCENE_CORRELATED_PCM_CHANGE`. The four independent visual label changes again count **[47,47,47,47]** pixels.

**Crucial boundary:** the original `runtime-evidence/nexium-scenes-run.log` is **zero bytes**. The strict `guest-scene-trace-audit.json` reports `GUEST_TRACE_NOT_OBSERVED`, with null hardware latency. Pressing mapped Plus near the end did not make guest `fprintf(stderr)` observable to the runner. Thus the internal guest event timings are **NOT MEASURED** in this stage even though the NRO contains the trace formatter and CI is green. Do not infer a missing scene transition or zero response time from the absent guest log.

The prior workflow [39048925368](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39048925368) without the final Plus change also completed successfully; the later run is the authoritative screenshot and audio comparison for this stage. A separate intermediate integrated NRO run `39048634327` failed a negative test fixture before compilation, and its corrected test version passed host CI; do not misstate that failed run as a compiled binary.

### Stage 266: writable guest SD export with readback

The **current upstream NeXium source** places `sdmc:/` beneath `nexium_common::paths::sdmc_dir()`. The default is the `sdmc` subdirectory of NeXium's configuration root. It supports the environment override `NEXIUM_DATA_ROOT`; host CI can set that variable to an isolated temporary directory and retrieve `$NEXIUM_DATA_ROOT/sdmc/switch/vandal-hearts-remake/` afterward. This mapping has been inspected in upstream NeXium code; **writing the actual CSV in this project is not yet implemented or tested**.

Implement a separate bounded numbered scene-trace CSV exporter **after the audout worker joins**, using temporary write, close, readback verification and rename without overwriting prior captures (matching the existing hardened audio-diagnostics protocol). The NeXium workflow must collect that SD file and verify exact event/order/serial semantics before declaring any measured guest-origin delays. Any absence or corruption must be an explicit not-observed/failure verdict; never silently substitute host-side input events.

The physical Switch remains **HARDWARE NOT TESTED**.
