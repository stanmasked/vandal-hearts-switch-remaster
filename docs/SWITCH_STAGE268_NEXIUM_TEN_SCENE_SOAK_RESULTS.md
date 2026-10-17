# Stage 268 — ten alternating music-scene transitions in NeXium

**Result: TEN_GUEST_SCENE_TRANSITIONS_DUAL_TRANSPORT_VERIFIED.** Native Switch hardware remains **HARDWARE NOT TESTED**. This result verifies internal emulator observations, not physical audio output or a retail soundtrack.

## Actual CI and independently verified artifact

- [GitHub Actions run 39056650199](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39056650199): both build and NeXium jobs completed **SUCCESS**, including `Capture ten additional A/B transitions in isolated NeXium` and `Require long-run guest optical SD and PCM consistency`.
- Published evidence artifact **12109718303**, `nexium-runtime-evidence`; independently downloaded as a real ZIP. Metadata SHA-256: `6387f6df3d3746ae5b14489ec56c0132565e0f75688d1b2143f35bd2269314da`. All **63 archive members passed ZIP CRC**.
- Soak capture: **61.049 s** of s16le stereo 48-kHz PCM; 11 captured UI screenshots representing initial FIELD and ten alternating FIELD/FOCUS transitions.
- Visual status-label pixel-change counts, independently read from the published machine report: **[47,47,47,47,47,47,47,47,47,47]**.
- Source `runtime-evidence/scene-soak/soak-guest-optical.csv` and separate original candidate `runtime-evidence/scene-soak/soak-sd-unverified.csv` have **1,632 bytes each** and are **identical byte-for-byte**, independently verified from the downloaded archive. Their shared SHA-256 is `941537c0c81b2ad687439de1e282119491c5de46580e2d701f063c0d2c7de05f`.
- The canonical CSV contains **53 events**: 10 INPUT, 10 POST, 11 ACCEPT, 11 SUBMIT_CALL and 11 RELEASE_RETURN (the additional acceptance/submit/return events belong to initial serial 0). Event serials 1–10 are complete, and no event-slot overflow is reported.
- Optical packet SHA-256: `cce50d7579452cfd014d64819309ad27aa1ad649c6f1a5f7a3f61a66df9f7d0e`; CRC32 `1327e9f8`. Original image and SD evidence are saved separately; neither is substituted by a synthetic fixture.

## Observed guest-only timing, ten complete transitions

| Interval | Median | p90 nearest rank | Max | Observed values > 50 ms |
| --- | ---: | ---: | ---: | ---: |
| Game loop observes input → music cue accepted | 17.477 ms | 31.486 ms | 33.525 ms | 0 |
| Game loop observes input → first PCM submit/recovery returns | 49.081 ms | 52.410 ms | 65.147 ms | 3 |
| First PCM submit/recovery call → return | 25.804 ms | 33.073 ms | 33.277 ms | 0 |

The PCM one-second settled-window **zero-crossing proxy** is consistently higher for each FOCUS state than each FIELD state. FOCUS values: 577, 586.75, 571.5, 596 and 605.5 Hz. FIELD values: 326, 316, 325.5, 321, 325 and 324.5 Hz. These numbers are waveform classifiers, **not actual musical fundamental pitch measurements** or timing alignment between host and guest clocks.

## Scope and limits

The five complete event groups per music change support a repeatable **guest-internal phase timeline** under NeXium. The trace capacity is **64 records**; this 10-transition run used 53 slots and dropped 0. Additional sequential transitions would eventually exceed capacity; the current witness must not silently overwrite or fabricate events.

**Crucially, zero dropped trace rows does not mean zero audio underruns.** Only the first submission/return after each scene change was recorded, not a continuous stream of every audout page in the session. The sample in the returned page might also have been generated prior to the scene change. No continuous guest-side audio queue occupancy or device DAC playback onset was measured. Virtual PulseAudio PCM cannot establish physical speaker output. Neither host frame/PCM offsets nor guest timestamps alone prove causal input-to-physical-sound latency.

The optical and virtual SD paths were corroborated in this session. Their consistent output does not prove FAT durability after power loss, console HOME/sleep correctness, original soundtrack authenticity, or behavior on real Switch hardware.

## Next direction

Add **bounded, continuously sampled audio lease/queue telemetry** to the dedicated audio worker, with precise definitions of what the queue APIs actually report. Keep the event trace of cue transitions separate from per-page operational observations and avoid unbounded logging, blocking or allocation inside the audio callback. Before claiming an underrun, obtain an explicit queue starvation/recovery signal rather than inferring it from a transient low PCM RMS. Hardware testing must remain independently gated.
