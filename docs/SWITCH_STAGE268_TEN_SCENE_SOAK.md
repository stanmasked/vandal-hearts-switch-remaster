# Stage 268 — ten-transition NeXium guest music soak

**Status at documentation creation:** new host and NRO regression code committed; GitHub Actions [39056001836](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39056001836) has a successful build/test job, while its second emulator job must be reviewed before declaring the long soak successful.

## Goal and scope

Repeat the controlled `FIELD→FOCUS→FIELD` switch **five times** in a *fresh guest process*, with **ten** A/B input transitions, rather than the two cycles verified in Stage 267. No retail audio assets, keys, firmware or game images are included. The candidate guest remains the pinned integrated homebrew NRO from [build 39052705390](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39052705390), SHA-256 `58a438082f282ba279044d2a25fc1369e8493571a67b2082da41e0d8c0405929`.

One startup event triple plus five guest trace kinds per each of ten transitions should fill **53 of the 64 immutable trace slots**: three startup events plus 10 × (INPUT, POST, ACCEPT, SUBMIT_CALL, RELEASE_RETURN). An additional event, lost event, unmatched serial, conflicting scene or nonzero dropped counter must **not** be declared a complete verified soak. There is no overwrite/rolling buffer.

## Real input / audio / screenshot witness

`tools/capture_nexium_scene_soak.sh` uses a **new isolated** `NEXIUM_DATA_ROOT` beneath runner temporary storage, distinct from the Stage 267 4-transition recording. It starts a new pinned NeXium guest process and PulseAudio null-sink monitor, records aligned host PCM byte offsets and wall-clock marker rows, and screenshots all 11 states. Every other button is A (NeXium key C) and B (key X). It requests the existing X+Plus diagnostic shutdown only **after** the tenth transition, takes a real framebuffer screenshot containing the post-join guest optical packet, and lists actual files on the isolated emulated SD root.

`tools/audit_nexium_scene_soak.py` does not generate any evidence. It requires:

1. Real optical screenshot decoded using the existing 924-byte CRC32 protocol, with exactly **53** guest trace events, **zero dropped**, three startup serial-zero events and ten complete, serial-ordered transitions alternating scenes 2 and 1.
2. A separate, exact byte-for-byte matching guest SD CSV from the same isolated root; a missing, duplicate or changed file fails the evidence gate.
3. Exactly eleven 1280×720 UI screenshots with ten meaningful music-label changes in the known NeXium framebuffer region. These show the visible user state, not acoustic output.
4. A real 48-kHz stereo s16le monitor PCM stream and eleven settled **one-second** waveform intervals, after 1.35 s of each host marker and at least 0.5 s before the next marker. Each must be non-silent; full-scale hard clipping is checked across the entire capture; focus/field zero-crossing rate classes must be separated by at least 15%. A crossing rate is a frequency proxy, **not a pitch or score identity**.
5. Positive and negative synthetic regressions in `tests/test_audit_nexium_scene_soak.py` for ten-scene success, corrupted SD bytes, missing UI image, wrong host marker, incorrect guest serial, nonzero drops, whole-PCM clipping, and identical scene frequencies.

Report guest-internal INPUT→ACCEPT, INPUT→RELEASE_RETURN and SUBMIT_CALL→RELEASE_RETURN medians, 90th-percentile nearest-rank values and maximum, with counts of intervals over 50 ms. A large internal wait is **an observation, not by itself a proof of buffer underrun**. The trace only captures the *first* PCM page after cue acceptance; it cannot exclude underruns on subsequent pages.

## Comparison basis from independent Stage 267 recordings

| Run | Guest INPUT→ACCEPT median | Guest SUBMIT_CALL→RELEASE_RETURN median | Guest INPUT→RELEASE_RETURN median |
| --- | ---: | ---: | ---: |
| [39053160279](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39053160279) | 16.675 ms | 32.530 ms | 48.977 ms |
| [39053726025](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39053726025) | 14.022 ms | 33.287 ms | 49.004 ms |

These earlier distributions contain only four transitions each; the new ten-transition series increases the number of observations but is still one emulator session and does not constitute a real-time guarantee.

## Explicit evidence limits

NeXium guest timestamps are in an emulated `armTicksToNs(armGetSystemTick())` domain, while host `parec` file positions have buffering delay and wall-clock values come from Linux. **There is no established clock calibration across guest and host**, so do not subtract their absolute timestamps or equate PCM byte-file delay with guest input-to-DAC latency.

No full-scale clipped samples and a zero guest trace overflow counter **do not prove** no audout underruns, exact looping, retail soundtrack, actual speaker playback or hardware timing. Physical Nintendo Switch status remains **`HARDWARE NOT TESTED`**.
