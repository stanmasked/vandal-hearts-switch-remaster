# Vandal Hearts Remake — Stage335: independent replay of three genuine NeXium capture cohorts

The newly completed [NeXium runtime run #39175592570](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39175592570) confirms a **third genuine NRO emulator execution** after original prior recordings [#39166023593](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39166023593) and [#39167324026](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39167324026). Its original Stage304/305 strict checks and Stage334 source-bound guest/host compact manifest succeeded.

| Guest software-call source measurements | Original #1 | Original #2 | New original #3 |
| --- | ---: | ---: | ---: |
| Final successful normal `audoutPlayBuffer` software duration | 11,225,937 ns | 22,352,500 ns | **18,486,979 ns** |
| Lower median of previous calls | 32,154,011 ns | 31,247,083 ns | **32,374,948 ns** |
| Previous median minus final software call | +20,928,074 ns | +8,894,583 ns | **+13,887,969 ns** |
| Host wall-clock first/second event interval | 357 / 4,270 ms | 358 / 4,286 ms | **324 / 4,221 ms** |
| Host monotonic first/second event interval | 357,687,151 / 4,269,790,190 ns | 357,696,182 / 4,285,779,743 ns | **324,470,642 / 4,220,779,386 ns** |

Guest software durations and host recorder intervals are **not synchronized**. The third virtual PulseAudio recording confirms that source-captured PCM digital signals exist, not what comes out of a real Switch speaker. Original PS1 soundtrack fidelity and Plus-induced audio dropouts remain unverified.

Stage335 adds `tools/compare_nexium_stage335_three_original_capture_sources.py`, thirteen synthetic source tamper/independence/privacy regression tests, and a dedicated original archive replay. The analyzer downloads and re-audits the same nine original files independently for **all three captured runs**, including exact original Stage320/322 guest records, Stage325 host-clock observations, and strict Stage304/305 original successful receipts.

The original first and second per-run four source SHA-256 digests are pinned in `tools/nexium_stage335_first_two_original_source_pins.json`. For the third run, the auditor independently recomputes Stage334 and requires its result to exactly equal the **original archived Stage334 receipt**; it also requires all four SHA-256 source classes to differ across three runs. It publishes only guest software intervals, host-only event deltas and original source digests; no absolute epochs, PCM or sound assets.

**Evidence boundary:** 3 successful distinct emulator executions are better evidence of repeatability than 576 synthetic omissions of the original two sets, but these are still small selected guest software and host recordings, **not a population confidence interval**, a real Nintendo Switch hardware test, speaker delay measurement, or proof the emulator represents physical audio behavior. No SPU, `audoutPlayBuffer`, PCM generation, tactical gameplay or original strict Stage304/305 verification logic changed.

## Independently confirmed three-original-capture result

[Stage335 workflow #39176524278](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39176524278) **completed successfully**. All **13 original source and negative-control tests** passed, followed by re-downloading the three distinct originally successful NeXium evidence archives and reproducing each Stage334 guest/host source digest and bounded interval. The third saved Stage334 manifest matched an independently re-derived receipt **exactly**.

| Genuine source evidence | Original #1 | Original #2 | New original #3 |
| --- | ---: | ---: | ---: |
| Total normal `PlayBuffer` call attempts | 1,414 | 1,443 | 1,401 |
| Source-retained last calls | 16 | 16 | 16 |
| Previous successful calls before last | 15 | 15 | 15 |
| Last-call first-possible rank | 1 | 6 | **7** |
| Prior lower median minus last guest software call | +20,928,074 ns | +8,894,583 ns | **+13,887,969 ns** |

Third source's original SHA-256 digests, pinned by the successful source record and recomputed from the actual third archive:

| Original third NeXium source | SHA-256 |
| --- | --- |
| `audio-playbuffer-history-000.csv` | `083efbdbc3332593615b70df271ea5608fba13b06d2f2c6e5c779b7762f3a909` |
| `audio-last-playbuffer-000.csv` | `b9dd9c6875526fbb7f796d0b6766e95532e283d5f9d42bb80a063b3f43883a97` |
| `scene-exit-controls.csv` | `452790e04711f1e0acbc87b5df3bb2e3d2351a412ce21d8c6560197fec2b0c5d` |
| `scene-exit-controls-monotonic.csv` | `7922f76062f9609a4acb994083f5c957d01cfb865348fabba94f0616467c0486` |

All four source digest types were distinct across all three runs. Stage335 compares **guest software duration to guest software duration**, and **host control interval to host control interval**, never guest software time to host recorder time.

**Evidence boundary remains unchanged:** three original emulator captures do not measure physical Nintendo Switch speaker behavior, original retail soundtrack fidelity, or audio quality perceived by a player.
