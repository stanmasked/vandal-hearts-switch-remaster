# Stage 262 — independently measured NeXium stereo PCM quality

**Scope:** offline analysis of the real virtual-sink recording from Stage 261. This is **not** a physical Switch hearing test, an identification of the retail soundtrack, or evidence of a scene change.

## Source and identity

- Source emulator CI: [run 39036800600](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39036800600), evidence artifact `12102846108`.
- The recording's parent emulator CI pinned build run `39034607288`, artifact `12101269376`, NRO SHA-256 `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`.
- Audio source: `runtime-evidence/nexium-monitor-s16le-48k.pcm` inside the original unmodified artifact.
- Independently computed raw-PCM SHA-256: `7266c432bc7078bc8ee7a636cbb8d8bdb27ff52e2041f37766b90d22e305258d`.
- The monitor is a **virtual PulseAudio null sink** connected to the NeXium process. User-supplied original music was not present.

## Exact measurements

A standalone standard-library tool `tools/analyze_nexium_pcm.py` analyzes raw signed stereo 16-bit little-endian 48-kHz PCM and records a time-resolved RMS envelope using 4,800-frame (100-ms) windows. Five host-only synthetic regression methods test stereo separation, all-zero windows, partial windows, hard clipping, wrong digests, malformed lengths and symlink refusal.

| Measurement | Observed |
| --- | ---: |
| Raw bytes | 8,657,264 |
| Stereo frames | 2,164,316 |
| Duration | 45.090 s |
| Left-channel RMS | 573.798 |
| Right-channel RMS | 646.605 |
| Left-channel peak magnitude | 2707 |
| Right-channel peak magnitude | 2879 |
| Mean DC L / R | -50.743 / -48.915 |
| Full-scale clipping count L / R | 0 / 0 |
| RMS of stereo channel difference | 442.424 |
| Pearson correlation of channels | 0.7417 |
| 100-ms RMS windows | 451 |
| Windows with RMS below 32 | 8 |
| Longest consecutive low-RMS interval | 0.800 s |

**Interpretation:** Signal exists, left and right contain distinct information and no sample reached the full-scale s16 clipping threshold. The lowest-RMS spans may be ordinary musical rests or startup delays. Neither a correlation value nor the recurring RMS envelope proves byte-exact looping, correct tempo, scene switching or lack of audible artifacts. An 0.8-second low-level interval must not automatically be called an underrun.

A preliminary independent autocorrelation of the RMS envelope shows high energy-pattern similarity at offsets near 1.2, 2.3 and 3.5 seconds; this is *not* a proven sample-accurate loop period and is not currently a CI assertion.

## Regression and CI

- Tool: `tools/analyze_nexium_pcm.py`.
- Tests: `tests/test_analyze_nexium_pcm.py` (5 test methods).
- Local Python regression result: `Ran 5 tests ... OK`; original waveform independently analyzed and verified.
- CI workflow `.github/workflows/emulator-smoke.yml` now runs these five regressions, stores `runtime-evidence/pcm-quality-report.json`, parses the report and requires a non-silent virtual trace of sufficient duration without full-scale clipping. That check is **only a virtual-trace consistency test**, not audible or retail-music acceptance.
- At documentation creation, the new CI run [39037532462](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39037532462) was triggered; its final result must be checked before calling the new CI gate successful.

## Open questions

- No controlled A/B comparison between `MUSIC FIELD` and `MUSIC FOCUS` within the virtual audio capture yet.
- No source-identified SEQ/VAB or real PS1 game music was verified.
- No spectral listening or distortion verdict from physical speakers.
- Nintendo Switch HOME, sleep, SD durability and actual audio remain **`HARDWARE NOT TESTED`**.

Do not confuse this host audio trace with original CD/PS1 timings or the native Switch DAC.

## Confirmed full CI and published evidence

Follow-up workflow [39037532462](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39037532462) on exact code SHA `b7bc27287615846a711b1b4b89d413395aca474d` completed `success` in both jobs. The primary build-job log separately confirms `Ran 5 tests` and `OK` for `test_analyze_nexium_pcm.py`. The NeXium job completed graphics/input testing, virtual PCM capture, `python3 -m json.tool` validation and the strict `Verify captured audio measurements` step.

The published evidence ZIP is artifact **`12102842650`** (`nexium-runtime-evidence`). It was downloaded and independently verified: all ZIP CRCs passed, `runtime-evidence/pcm-quality-report.json` parsed without modification, its recorded SHA-256 matched the *raw* `nexium-monitor-s16le-48k.pcm` member, and a separate local execution of the analyzer reconstructed the **entire JSON report**, including all 451 window RMS entries, byte for byte in data meaning.

| New capture property | Value |
| --- | --- |
| Raw PCM SHA-256 | `b6a28499459381871247e51475e65b3063dca39e56356a38feadde0ce03e2113` |
| Bytes / frames | 8,656,916 / 2,164,229 |
| Duration | 45.088 s |
| RMS left / right | 566.074 / 637.807 |
| Peaks left / right | 2707 / 2879 |
| Channel correlation | 0.7416 |
| Clipped sample count | 0 / 0 |
| 100-ms low-RMS windows | 8 of 451 |
| Longest low-RMS streak | 0.800 s |
| Observation | `NONZERO_MONITOR_PCM` |

These measurements vary slightly between emulator runs (recording boundaries and timing are not deterministic), but both recordings show the same narrow class of results: nonzero distinct stereo channels, no observed full-scale clipping, and brief low-level windows. There is **still no controlled change of music scene, no proven original soundtrack and no physical audio playback**. Hardware status remains exactly `HARDWARE NOT TESTED`. The following documentation-only commit is not the SHA that was executed by CI.
