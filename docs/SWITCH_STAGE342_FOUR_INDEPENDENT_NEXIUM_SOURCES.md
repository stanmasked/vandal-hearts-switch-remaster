# Stage342: four genuine independent NeXium guest audio source captures

This source audit is **conditional on the entire fourth original NeXium run #39182548276 succeeding**, including unchanged strict Stage303–305, Stage334 and Stage336 checks. It never treats a queued, incomplete, or failed run as a confirmed fourth source. It independently downloads the original source artifacts from runs #39166023593, #39167324026, #39175592570 and #39182548276.

The four-source comparator replays original guest PlayBuffer software histories, host-only recorder clock deltas, source SHA-256 pins and strict original PCM success receipts. It binds the third and fourth source archives to their **own** NRO build SHA, run ID, attempt and capture-time PCM monitor report. It separately crosschecks the later PCM quality report rather than confusing it with NRO-bearing recorder metadata. It rejects duplicate guest/host CSVs and source mismatches; it never mixes guest clock durations with host PCM sample timing.

The failed fourth attempt #39177437951 had an original backwards host wall-clock recorder-stop interval of −87 ms and is excluded. The subsequent run #39179079695 passed strict PCM checks but originally failed Stage336 due to a report path error; its **retrospective** re-audit succeeded in Stage341 but its original full workflow remained failed. Neither rejected run is used as an original accepted fourth cohort here.

**Evidence limitations:** Software-call service durations and recorder intervals are not independent measurements of physical Nintendo Switch speakers, DAC quality, original PS1 soundtrack fidelity, or causally established audible audio dropout. Stage342 must finish green in addition to the fourth original full runtime workflow before its four-source comparison can be described as independently verified.


## Verified completed source evidence

[Original fourth NeXium #39182548276](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39182548276) **PASSED** the NRO build, unchanged Stage303–305, Stage334 and corrected Stage336. [Independent four-run audit #39183433971](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39183433971) also **PASSED** 13 Stage337 and nine Stage341 tests, downloading and source-verifying all four original capture archives.

| Original software/host measurement | First | Second | Third | Fourth |
| --- | ---: | ---: | ---: | ---: |
| Last successful guest PlayBuffer software bracket (ns) | 11,225,937 | 22,352,500 | 18,486,979 | **25,438,021** |
| Previous 15 guest software-call lower median (ns) | 32,154,011 | 31,247,083 | 32,374,948 | **26,170,625** |
| Last-call rank in source window | 1 | 6 | 7 | **7** |
| Host first-control monotonic interval (ns) | 357,687,151 | 357,696,182 | 324,470,642 | **350,024,814** |
| Host second-control monotonic interval (ns) | 4,269,790,190 | 4,285,779,743 | 4,220,779,386 | **4,269,756,021** |

All four original captures' last guest service calls were shorter than their own preceding-call medians. The third and fourth *different original source runs* executed **bit-identical NRO** SHA-256 `1ddd4eb8ca74ec1234973cfdfa5c46b4e8af0fea770962151b317b333a1b766c`, but recorded different software service-call durations. The fourth-minus-third guest software last-call difference is **+6,951,042 ns** and prior lower median difference **−6,204,323 ns**. This is not proof of a causal audio glitch, hardware latency, original soundtrack fidelity, or guest-to-host clock alignment.
