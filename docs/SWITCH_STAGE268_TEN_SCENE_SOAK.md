# Stage 268 — ten-transition NeXium guest music soak

**Final result: TWO INDEPENDENT LONG-SOAK EMULATOR RUNS SUCCESSFUL.** Validated 10 transitions and 53 guest events in each, with zero trace drops. Physical Nintendo Switch remains **`HARDWARE NOT TESTED`**.

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

## Completed verification and correction of an initial false-negative

The first end-to-end [run 39056001836](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39056001836) **FAILED** at the new long-run audio gate, not at scene selection or optical decoding. Its original artifact `12109547827` was independently examined: all ten guest serials were complete (53 rows, dropped=0), packet CRC32 `6be3d597` matched, screenshots changed and the 11 genuine settled music windows contained nonzero audio. The failure came from choosing the *midpoint of the unbounded final monitor interval*: after Plus ended the guest, PulseAudio kept recording several seconds of silence, which was incorrectly interpreted as silent `MUSIC FIELD`. This is **not evidence of an audio buffer underrun**.

Commit `e99f1459d259676d0543c87a48a3614c2ffeef6e` corrected the interval selection: analyze the first full second **after a fixed 1.35-s scene-stabilization interval**, rather than searching the middle of the open-ended recording tail. Commit `3e47818621ebb4b6f51464f9cb579d17ab4ac623` added a negative/positive regression for **six seconds of monitor silence following normal shutdown**. Commit `c3c7ccd090ff9718ba3204ac5c1856aa5b6f82cc` also preserved a separately labeled `soak-sd-unverified.csv` source copy in the artifact for independent forensic comparison; the strict test still rereads the original guest SD file and never treats the convenience copy as a substitute.

### Two green GitHub Actions runs

| Check | First verified long soak | Second verified long soak |
| --- | --- | --- |
| GitHub Actions | [39056584248](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39056584248) | [39056650199](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39056650199) |
| Code commit | `3e47818621ebb4b6f51464f9cb579d17ab4ac623` | `c3c7ccd090ff9718ba3204ac5c1856aa5b6f82cc` |
| Workflow | **SUCCESS**, build + NeXium jobs | **SUCCESS**, build + NeXium jobs |
| Runtime evidence artifact | `12110375143` | `12109718303` |
| ZIP SHA-256 | `70090ab502c38513fa32fa5be63b24269e4dbf788d80a63d3bca75449acaf5ad` | `6387f6df3d3746ae5b14489ec56c0132565e0f75688d1b2143f35bd2269314da` |
| ZIP members / failed CRC checks | 62 / **0** | 63 / **0** |
| Guest events / dropped | **53 / 0** | **53 / 0** |
| Complete alternating scene serials | **10** | **10** |
| Pixel differences at each scene-label switch | **47**, all ten | **47**, all ten |
| Recorded stereo PCM | **61.033 s** | **61.049 s** |
| Lowest genuine settled 1-second RMS | **541.323** | **504.377** |
| Maximum FIELD zero-crossing proxy | **330.0 Hz** | **326.0 Hz** |
| Minimum FOCUS zero-crossing proxy | **555.5 Hz** | **571.5 Hz** |
| Full-scale clipping samples | **0** | **0** |

In the second run an entirely separate independent Python script decoded all **7,392 packet bits from the actual screenshot**, recomputed the guest CRC32 and events, evaluated ten visible status-label changes, scanned the PCM for hard clipping and reconstructed the timing summaries. The guest SD copy stored as `soak-sd-unverified.csv` in the uploaded ZIP was compared **byte-for-byte** against the independently reconstructed optical CSV. The two 1,632-byte CSVs match exactly, SHA-256 `941537c0c81b2ad687439de1e282119491c5de46580e2d701f063c0d2c7de05f`. The original guest file was already independently validated by the CI gate before upload. First and second session CSV digests differ, proving they are not reused captures.

### Ten-transition guest-software timing statistics (milliseconds)

`p90` is **nearest rank**, not interpolated, on just the ten complete internal intervals.

| Interval statistic | First successful run | Second successful run |
| --- | ---: | ---: |
| INPUT→ACCEPT median | 16.505 | 17.477 |
| INPUT→ACCEPT p90 | 33.699 | 31.486 |
| INPUT→ACCEPT maximum | 39.232 | 33.525 |
| INPUT→RELEASE_RETURN median | 48.663 | 49.081 |
| INPUT→RELEASE_RETURN p90 | 62.355 | 52.410 |
| INPUT→RELEASE_RETURN maximum | 65.926 | 65.147 |
| SUBMIT_CALL→RELEASE_RETURN median | 27.094 | 25.804 |
| SUBMIT_CALL→RELEASE_RETURN p90 | 35.271 | 33.073 |
| SUBMIT_CALL→RELEASE_RETURN maximum | 35.966 | 33.277 |

These timings describe the guest's observed input processing and the **first** PCM page after each music-cue acceptance, under emulator scheduling. Longer waits are not automatically underruns. The host is **not clock-synchronized** to guest audio, the final PulseAudio silence is excluded from the genuine musical scene analysis, and the 10-transition sample is not a statistical proof of worst-case latency. Neither run proves acoustic sound onset, exact original score, sample-perfect looping, absence of later PCM page underruns, SD power-loss durability, or real Nintendo Switch performance. **`HARDWARE NOT TESTED`**.

**Stage 268 conclusion:** `TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED` in two distinct NeXium emulator runs. The `main` branch is not changed by this work.
