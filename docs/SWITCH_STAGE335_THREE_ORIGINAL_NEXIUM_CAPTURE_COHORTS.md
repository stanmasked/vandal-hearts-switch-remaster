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

The independent Stage335 workflow must complete successfully before claiming all three original archives were independently re-validated together.
