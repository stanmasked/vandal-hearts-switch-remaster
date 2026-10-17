# Stage 264 — bounded host-relative detection of NeXium music-scene changes

**Scope:** independent analysis of previous NeXium PCM recordings using *host-buffered PCM-file offsets* recorded after A/B presses. This does **NOT** measure guest input-to-audio latency, exclude audout buffer underruns, prove original PS1 music, or test physical Switch speakers. **HARDWARE NOT TESTED.**

## Source provenance and code

- Exact guest NRO: build run [39034607288](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39034607288), artifact `12101269376`, build SHA `63c718679715adc809a3feb8845a15a37e645488`, NRO SHA-256 `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`.
- First scene recording: [run 39038902169](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39038902169), evidence `12102384340`. Overall workflow **failed a wrongly positioned screenshot-crop assertion**, even though scene PCM acquisition passed. Therefore **do not call this run successful**.
- Second scene recording: [successful run 39039097220](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39039097220), evidence `12102909959`, with confirmed screenshot states and A/B inputs.
- The stage 264 analysis code `tools/analyze_nexium_transition_timing.py` and synthetic tests `tests/test_analyze_nexium_transition_timing.py` use the unchanged NRO's previous raw PCM, not a simulated waveform for the reported real measurements. Five host regression tests also exercise synthesized positive and negative controls.

## Detection algorithm (deliberately not an input-to-audio latency measurement)

1. Revalidate exact five-state scene evidence with `analyze_nexium_scene_audio.py`. If neither focus nor field separates robustly by 15% across all windows, return `INSUFFICIENT_SCENE_SEPARATION`, not a fabricated delay.
2. Choose a scene-class threshold from **the gap between observed settled FIELD and FOCUS zero-crossing estimates** in that same recording. For each of four markers, analyze 300-ms stereo PCM windows beginning 0, 100, 200 ... up to 1600 ms after the marker; each window must exceed a low-RMS threshold and classify as the expected new scene.
3. Require **three consecutive overlapping windows** of the new class. Report both the first qualifying window's start and the **end of the three-window confirmation** (window length 300 ms plus 2 × 100-ms hop). Do **not** call either value the guest response latency: the marker is generated from a buffered file-length snapshot taken after the input keypress and can lag the guest action.
4. Independently count 10-ms PCM windows with combined RMS below 32 within 500 ms *before* and 1500 ms *after* each marker, the longest contiguous run and samples reaching full-scale s16. Musical rests, note envelopes and emulator buffering cannot be distinguished from genuine audout xruns from this monitor alone.

The tool reports `actual_input_to_audio_latency_ms: null`, `audio_underruns_not_proven_or_excluded: true`, and `HARDWARE NOT TESTED` **even on fully passing runs**.

## Two independently captured runs

| Transition | Recording 1 confirmation end | Recording 2 confirmation end |
| --- | ---: | ---: |
| FIELD → FOCUS 1 | 600 ms | 600 ms |
| FOCUS → FIELD 1 | 500 ms | 500 ms |
| FIELD → FOCUS 2 | 600 ms | 700 ms |
| FOCUS → FIELD 2 | 500 ms | 500 ms |

- First recording scene classifier threshold: 436.939 Hz (zero-crossing proxy), second 419.693 Hz. Neither number is a note pitch or a tempo claim.
- The first confirmed 300-ms window began at 100/0/100/0 ms relative to the four markers in recording 1; at 100/0/200/0 ms in recording 2.
- Longest contiguous 10-ms-window low-RMS span within transition neighborhoods: at most **30 ms** in recording 1, **60 ms** in recording 2. These are **observed waveform properties**, not a diagnosis of buffer delivery.
- Neither recording had a full-scale `±32767`-threshold value in the measured two-second transition neighborhoods.
- Stable scene detection occurred in all eight observed transitions. This supports reproducible **host-relative classification**, not sample-accurate musical transition latency or exact Switch timing.

## Regression and CI

- New standard-library tool and five synthetic tests have been locally executed with `Ran 5 tests ... OK`. Tests include identical FIELD/FOCUS signals, deliberate silence, malformed markers and explicit rejection of hardware/tempo claims.
- GitHub workflow `.github/workflows/emulator-smoke.yml` runs these tests as part of its build, calculates `runtime-evidence/scene-transition-observations.json` after the full NeXium A/B capture, and checks four classified events and safety fields. The source run is [39040155757](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39040155757), code SHA `8e2d628668f20301488f78515cee5f5297faf1f1`. Verify its final workflow status and independently rerun the analysis on the artifact before claiming end-to-end CI success.

**Next accuracy prerequisite:** collect clock-aligned **guest input receipt, accepted scene cue, audout page queue/release and host monitor playback** events. Current file-size snapshots are insufficient for exact latency or true underrun detection. This should be instrumented in a bounded, nonblocking manner that never blocks the audio callback or injects console assets.

## Actual new NeXium CI: complete and independently verified

The experimental NeXium workflow [39040155757](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39040155757) **completed SUCCESS** on code SHA `8e2d628668f20301488f78515cee5f5297faf1f1`, with successful build/tests and runtime jobs. The primary job log explicitly reports the **five new `test_analyze_nexium_transition_timing.py` regressions passed**. The separate Host SPU run `39040155784` and Native PCM transport run `39040155703` also completed SUCCESS on this SHA.

Published [NeXium runtime evidence artifact `12104255690`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39040155757) was independently downloaded and inspected. All **33 ZIP members** passed CRC. Its actual scene PCM hash is `sha256:16d271396dbc2e57ff66fc32ac8cacbb4e7cf66f2235834e731bad7bc074abdb` (7,802,308 raw bytes, **40.637 s**). Scene evidence again reports `REPEATED_SCENE_CORRELATED_PCM_CHANGE`, focus/field ZCR proxy ratio **1.7527**, and visual label differences **[47, 47, 47, 47]** pixels. This recording is distinct from the two historical observations above.

| New run transition | First confirmed analysis window begins | Three-window confirmation finishes | Longest low-RMS span |
| --- | ---: | ---: | ---: |
| FIELD → FOCUS 1 | 200 ms | 700 ms | 50 ms |
| FOCUS → FIELD 1 | 0 ms | 500 ms | 20 ms |
| FIELD → FOCUS 2 | 100 ms | 600 ms | 30 ms |
| FOCUS → FIELD 2 | 0 ms | 500 ms | 30 ms |

The stable-scene classification threshold (zero-crossing proxy) was **425.207 Hz** in this new recording. No transition-neighborhood samples met the full-scale clipping threshold. This does **not** constitute hardware latency or proof of no underruns.

A separate local rerun of `tools/analyze_nexium_transition_timing.py` using the newly downloaded `nexium-scenes-s16le-48k.pcm` and `scene-events.csv` produced **exactly the same entire structured JSON** as `scene-transition-observations.json` from GitHub CI. This independently binds all reported figures to the actual recorded bytes. The run does not prove original Vandal Hearts music, physical speaker audio or actual device response times; **HARDWARE NOT TESTED** remains unchanged.
