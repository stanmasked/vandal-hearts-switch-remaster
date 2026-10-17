# Stage 263 — two controlled music-scene transitions in NeXium

**Result: EMULATOR SCENE-CORRELATED SYNTHETIC PCM CHANGE CONFIRMED.**
Real retail Vandal Hearts music, physical speakers and physical Switch execution remain **NOT VERIFIED**; hardware status **`HARDWARE NOT TESTED`**.

## Exact software and source evidence

- Successful CI: [Experimental NRO runtime smoke test run 39039097220](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39039097220), workflow/code Git SHA `cdf96b609edef17b6705c7ff97db00233dcb8d83`. Both the build/test and NeXium runtime jobs succeeded.
- The run **did not substitute** its newly built NRO for the audio candidate. It downloaded and verified the pinned integrated libnx/audout NRO from [run 39034607288](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39034607288), artifact `12101269376`, build SHA `63c718679715adc809a3feb8845a15a37e645488`, binary SHA-256 `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`.
- Original [emulator evidence artifact `12102909959`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39039097220) (`nexium-runtime-evidence`) contains original screenshots, original PCM bytes, host event markers, full NeXium/PulseAudio logs and both scene reports.
- Runtime: NeXium Linux nightly, headless Xvfb and Lavapipe Vulkan. ALSA routes to a virtual PulseAudio monitor. A/B inputs were sent through Xdotool: `c` maps to controller A (select), `x` to B (cancel).

## Controlled sequence, independent verification

The protocol `tools/capture_nexium_scene_audio.sh` executes and screenshots exactly five sequential states:

`FIELD(initial) → FOCUS(1) → FIELD(1) → FOCUS(2) → FIELD(2)`

The host logs PCM-file byte lengths and wall-time at every action; markers are **approximate buffered host positions**, **not** guest audio-service or hardware timestamps. The analysis excludes the first 1.5 s after each marker and the final 0.5 s of each state before the next action.

The 40.322-second signed s16le 48-kHz stereo PCM capture independently produced:
- Raw PCM SHA-256: `6726557d6e9ce7ae2f2ef0539f32104671db8a295c49d2c62c6cac922ff0feb0`.
- Median zero-crossings frequency proxy, FIELD: **306.182 Hz**; FOCUS: **545.479 Hz**; ratio **1.7816×**.
- All five stable intervals had non-silent L/R RMS. Both focus intervals measured higher zero-crossing rates than **all three** field intervals.
- Per-state screenshot status-label crop changed by **47 pixels on each of the four switches**; this is the captured `MUSIC FIELD` / `MUSIC FOCUS` label, independent of the waveform.
- Conclusion from the strict, repeated-class-separation algorithm: `REPEATED_SCENE_CORRELATED_PCM_CHANGE`, **not** a claim of sample-accurate SEQ timing or soundtrack authenticity.

The evidence ZIP passed CRC validation; independent local rerun of `tools/analyze_nexium_scene_audio.py` reproduced **the exact JSON report**, and independent screenshot pixel-difference calculation reproduced all four visual scores. Synthetic tests `tests/test_analyze_nexium_scene_audio.py` ran **5/5 OK** in GitHub CI. Importantly, the tests explicitly reject five identical-frequency scenes as proof of a sound transition.

## Early diagnostic attempts and correction

The first [run 39038902169](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39038902169) captured and analyzed the scene changes successfully but its **workflow conclusion was failure** because the screenshot validation used an incorrect, too-low crop (y=660–708, the NeXium host UI). Original screenshots showed the label at approximately y=610 instead. The final passing run `39039097220` uses crop `(960,600,1140,638)`, so the CI failure was resolved without altering the tested guest NRO or relaxing the audio waveform criterion. Do not quote the failed workflow as an all-green run.

## Tooling and limits

- `tools/analyze_nexium_scene_audio.py`: bounded structure checks, consecutive event-marker validation, per-scene RMS and zero crossings, explicit separation rule.
- `tools/capture_nexium_scene_audio.sh`: exact five-state Xdotool script, NeXium screenshot capture, 48-kHz stereo PulseAudio recording.
- `tests/test_analyze_nexium_scene_audio.py`: five synthetic regressions including negative controls.
- `.github/workflows/emulator-smoke.yml`: invokes all tests, the scene capture and a separate visible UI status-change assertion.

**Limits:** zero-crossing rate is a frequency-domain proxy, not a precise musical pitch estimate. The separation is correlated with controlled A/B state changes and visible UI labels but cannot mathematically exclude all unrelated sound sources. No original game assets were included, the synthesized fallback is not a retail soundtrack. No physical Switch, speakers, HOME/sleep, SD durability or hardware latency have been tested.

This document was committed after the passing CI run; it does not retroactively change the run's code or binary SHA.
