# Stage 261 — virtual audio output captured from NeXium

**Status:** `EMULATOR_NONZERO_PCM_CAPTURED`. Original commercial music and physical Switch audio remain **NOT VERIFIED**; `HARDWARE NOT TESTED`.

## Exact build and machine evidence

- [GitHub Actions run 39036398289](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39036398289) succeeded (both build and emulator jobs), on workflow commit `d4484efa68a7e62824123f2e6cef259c447bda20`.
- Emulator run still downloads and checks the **pinned integrated audio NRO**, run `39034607288`, artifact `12101269376`, build SHA `63c718679715adc809a3feb8845a15a37e645488`, NRO SHA-256 `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`. The workflow's own newly built test NRO is **not** substituted for this binary in the emulation job.
- [Audio and video original evidence artifact `12102726183`](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39036398289): screenshot captures, `integrated-nro-preflight.json`, virtual-device configuration/logs, `pulse-sink-inputs.txt`, raw PCM recording and summary.
- Host: Ubuntu 26.04 runner, Xvfb, Lavapipe Vulkan, NeXium Linux nightly, PulseAudio isolated `module-null-sink` with ALSA pulse plugin. No host physical speakers were tested. The previous runner's `Unknown PCM default` ALSA errors did not establish sound; here a virtual default sink is intentionally configured.

## Independently checked raw PCM

Downloaded the published evidence ZIP, checked all ZIP CRCs and recomputed PCM measurements independent of the Actions step:

| Parameter | Observed |
| --- | --- |
| Raw monitor bytes | 8,658,668 |
| Sample format | signed little-endian PCM 16-bit stereo, 48,000 Hz |
| Interleaved sample values | 4,329,334 |
| Recorded duration | 45.097 seconds |
| Samples with magnitude >= 256 | 1,350,143 |
| Peak magnitude | 2,879 |
| RMS amplitude | 599.943 |
| One-second windows with RMS > 50 | 46 / 46, including the partial final window |
| PulseAudio sink input source | `application.name = "ALSA plug-in [nexium]"`, process binary `nexium` |

These observations establish **non-silent output from NeXium's host audio interface to a virtual sink while the pinned NRO was supplied**, not the identity of the guest musical content. Synthesis falls back to generated audio in the absence of user-owned SEQ/VAB on mounted SD. No original commercial music was bundled, and no subjective hearing test occurred.

The secondary time-limited audio launch's stderr ends with a winit/X11 connection panic during/near Xvfb shutdown; preserve that original log and do not infer a graceful close from the workflow's green badge. The *separate* graphical/input stage passed before audio recording began. Guest HOME/sleep, physical hardware audibility and long-term SD persistence remain untested.

## Review of the recording report

The first CI-generated `pcm-monitor-report.json` mistakenly contained a literal `\\n` token after the terminating JSON object. The independent audit read the raw JSON object after removing that invalid suffix; the underlying PCM WAV data and numeric measurements were verified directly, not accepted from the report alone. Follow-up workflow commit `f28f89ef0dbfe3d408ddf599f5d6d7f1224eb9dd` corrects the extra token, uses an explicitly NeXium-attributed sink input instead of a generic active-sink condition, and records the emulator process exit status. Results of that later commit require a separate CI run.

## Required next checks

- Re-run the updated workflow and verify the report is valid JSON with no trailing data.
- Independently check that nonzero capture comes from the virtual sink connected to the NeXium process, not unrelated host system playback.
- Allow manual listening to the WAV extraction only as a subjective emulator-host check. This cannot prove the original PS1 soundtrack.
- Continue physical console acceptance protocol for actual music, controller behavior, HOME, sleep and SD persistence before ever replacing `HARDWARE NOT TESTED`.
