# Stage364 — original guest PCM/tail triple independently binds to Stage363 host clocks

## Why Stage364 exists

The authenticated [NeXium #39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727) **succeeded**, including strict Stage303/304, original guest Stage313/348/351/357/360 and new host Stage362 recorder-stop dual clocks. [Stage363 #39344117035](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39344117035) separately succeeded by downloading the exact original archive and reauditing the original host clock sources, PCM SHA, raw guest Stage357/360 records and their receipts.

Stage364 expands the independent *raw guest* proof instead of trusting only high-level Stage348/351 receipt counters. The same old-source Stage352 triple-source audit library is reused on the **new successful run**: it reopens the actual Stage313 last audio-page CSV, original Stage314 source receipt, original Stage348 lease accounting CSV and Stage351 bounded-tail-reason CSV, rechecks all necessary prior receipts and rejects forged ownership or different archives. The results are then bound to the independent Stage363 verdict over the *same* source archive and run id.

## Exact extra source pins

| Original record | SHA-256 |
| --- | --- |
| `audio-exit-output-000.csv` | `c234be43860581ab47a7fc7760054d77767e0fcbeb38d72631d50e87df931cf3` |
| `guest-original-audout-last-page-stage314.json` | `7e6f360bda821110191c323acdc6e5e2f0041833dc7b6d39b530da55bb267b27` |
| `audio-lease-reconciliation-000.csv` | `2258d2e713bc3325dc51bd41345130fa102373f7cd24d1feeee31cb43ea7aef8` |
| `audio-exit-tail-reason-000.csv` | `6730ef1969efd9535a109db0f4aacb4c0deca9e95080a54da5f1ee04fc0754b3` |

All four are from NeXium #39340120727, not old #39325440778 (authentic guest `0xEA01`) or old failed #39333759265 (host stop clock regression). Remaining original receipt/source identities are already SHA-pinned in the independently reexecuted Stage363 auditor.

## Expected source-bound software facts

- Original bounded-tail result: Stage351 reason **7**, Stage357 raw service Result **0**.
- Original software buffer lease: **1438 acquired / 1438 released / 0 abandoned**.
- Stage303 original recorder-stop: **passed** strict wall/byte ordering; host recorder epoch delta **+21ms**.
- Stage362 companion host monotonic interval: **+20,788,687ns**.
- Last queue-depth probe is an *old pre-submit reading*, not a direct end-of-playback queue measurement. The old guest timeout run has no paired Stage360 probe sample.
- No guest ↔ host clock synchronization, hardware speaker/DAC output, PS1 retail music, or causal diagnosis of the previously failed host clock has been established.

The implementation `tools/audit_nexium_stage364_guest_host_triple.py` uses already established source auditors to reread the original archive, checks exact type-sensitive result fields, binds original run ID and source hashes and writes a compact exclusive JSON verdict. The separate [Stage364 CI workflow](../.github/workflows/stage364-authentic-guest-host-triple.yml) downloads the exact original NeXium archive. There are **14 synthetic mutation/unit controls** and a separate required actual-original-source replay. CI results are not assumed until observed.

No guest audio code, libnx service calls, ownership policy, 96-frame 48-kHz fade or 12ms bounded wait is changed.
