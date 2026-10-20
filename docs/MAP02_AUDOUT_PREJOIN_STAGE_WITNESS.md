# MAP02 research-only pre-join atomic audout stage witness

**Draft / DO NOT MERGE.** Child of [Draft PR #244](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/244) at original HEAD `d0e4c76085926669fed5495f77b812e8266fbe2a`. Previous stable main and parent source blobs stay immutable. **No licensed PS1 ROM, soundtrack, audio payload, or real Nintendo Switch speaker data is used.**

## Why this probe is needed

In repeated NeXium/PulseAudio trials, a **21-ms** guest host latency hint yielded 0 nonzero PCM samples and no final `VHPRE001` receipt, while **22 ms** yielded a CRC-valid receipt and all eight source PCM pages individually present in a virtual 48-kHz stereo recording. This failure is reproducible on the research host, but the cause remains unresolved.

The normal opt-in `VHPRE001` screen is drawn **only after** `vh_switch_game_audio_stop()` calls blocking `threadWaitForExit()`. A missing post-join packet therefore cannot by itself identify whether the audio owner did not initialize, failed while preparing PCM, is inside `audoutPlayBuffer`, is cleaning up or is merely waiting for the guest input/exit sequence.

## New opt-in guest atomic progress stages

Under **`VH_MAP02_AUDIO_PRESUBMIT_WITNESS=1` only** (default production=0), the audio worker publishes:

| Stage | Meaning at the last atomic store |
|---:|---|
| 0 | Worker not yet entered |
| 1 | Audio owner entered |
| 2 | `audoutInitialize()` succeeded and output format verified |
| 3 | Immediately before real `audoutPlayBuffer` |
| 4 | Immediately after **the function returned**, before lease validation |
| 5 | Cleanup code entered |
| 6 | Cleanup completed |

Two monotonically increasing counters record **call entrances** and **function returns**. A return is **not** proof of audible speakers or successfully released audio descriptor.

The main thread can make a **cooperative stop request without joining** using `vh_switch_game_audio_presubmit_request_stop()`. After a fixed **one-second** observation window, it draws an optical bitmap panel with ten checksum-protected byte rows (`A5 5A`, stage, saturated 16-bit counters, stop flag, XOR checksum and complement). The panel is shown for **8 seconds** before the existing code enters the potentially blocking join. Drawing uses the existing main-thread framebuffer and atomic loads only: no new filesystem I/O, locks, threads or libnx service calls from the render path. Audio PCM bytes and their original CRC/FNV8-page observer are unchanged.

**Important measurement effect:** this explicit one-second wait and eight-second panel **change the timing of guest shutdown** in research builds. Therefore successes/failures from this child may not be directly pooled with previous 21/22-ms CI results as if they were identical workloads. This experiment localizes stages; it does not change or establish a production latency threshold.

## Two separately captured screens

The dedicated NeXium workflow now captures:

1. `presubmit-guest-prejoin-stage.png` roughly three seconds after the final guest input, during the deliberate pre-join panel window.
2. `presubmit-guest.png` nine seconds later, after the panel's eight-second lifetime, when a successful worker join has displayed the original full 924-byte `VHPRE001` optical receipt.
3. `presubmit-guest-late.png` five seconds after that, for the original raster observation.

`tools/decode_map02_prejoin_stage.py` checks exact 1280×720 PNG dimensions, the magenta border, ten white/black byte rows, the two-byte panel identity, XOR checksum, stage range and non-inverted call counters. It writes `presubmit-guest-prejoin-stage.json` **even when absent**, with the explicit result `PREJOIN_STAGE_UNVERIFIED`. This diagnostic step uses `if: always()`; **the final existing `VHPRE001` eight-page CRC and independent real virtual PCM digest checks remain fail-closed**. Six generated-only PNG fixtures test valid return/entry, cleanup, absent border, corrupted checksum, impossible counters and geometry.

`.github/workflows/main-map02-audio-staging.yml` has child-only updated exact Git blob pins for precisely **three** reviewed opt-in files: `source/main.c`, `source/vh_switch_game_audio.c`, `source/vh_switch_game_audio.h`. All remaining source fingerprints stay pinned.

## Interpretation and acceptance

Examples:
- A **stage 3** snapshot with one more entry than return supports “the last observed guest execution entered the real audout call and has not yet published its return by the snapshot.” It is **not** proof of permanent deadlock, nor which host service failed.
- Stage 5 or 6 means the worker got as far as cleanup; a missing later `VHPRE001` would focus investigation on join/teardown or rendering without proving the cause.
- Stage 0/1/2 requires checking start, focus, service initialization and test input order before making conclusions.
- A missing/corrupted stage panel is **unverified**, not a phase-0 finding.
- The ten-row panel is a *single pre-join atomic snapshot*, not a time-series or synchronized CPU profiling record.

The optional guest CI may still intentionally fail at the 21-ms host hint. Check real child-run logs, PNG and JSON before classifying actual progress. **No physical Switch speaker/DAC or original PS1 game music fidelity has been tested.**

Parents #244/#242/#239/#234/#231/#229/#227/#225/#223/#218/#212 and `main` stay frozen. No merge.
