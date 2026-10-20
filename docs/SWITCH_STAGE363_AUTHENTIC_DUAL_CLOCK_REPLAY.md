# Stage363 — independently replay real successful NeXium Stage362 evidence

## Original execution

The fully completed, **SUCCESS** [NeXium workflow #39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727) executed NRO audio guest tests and **strict** Stage303 and Stage304 host PCM checks. Its original `nexium-runtime-evidence` artifact is `12229283873`. Stage362 ran on those actual NeXium capture files, not fabricated fixture clocks. The new [Stage363 workflow](../.github/workflows/stage363-original-dual-clock-replay.yml) is a separate replay that downloads **that exact previous run's artifact** and independently verifies the source files.

## Reproduced original source evidence (old/failed vs new/successful)

| Source observation | Old NeXium #39333759265 (FAILED) | New NeXium #39340120727 (SUCCESS) |
| --- | ---: | ---: |
| Original `scene-recorder-stop.csv` wall epoch difference | -771 ms | +21 ms |
| Host `scene-recorder-stop-monotonic.csv` clock difference | no original measurement | +20,788,687 ns |
| Buffered PCM byte difference across SIGINT stop | 0 | 0 |
| Final scene host PCM source bytes | 8,732,688 | 8,804,896 |
| Strict Stage303 stop source verdict | failed | passed |
| Stage362 original dual-clock pair | not recorded | passed |
| Guest Stage357 raw `audoutWait` result | 0 | 0 |
| Guest Stage351 original software exit reason | 7 (returned) | 7 (returned) |
| Guest Stage348 PCM lease acquired/released/abandoned | 1366 / 1366 / 0 | 1438 / 1438 / 0 |
| Retained old pre-submit probe's age at software tail begin | 125,833,907 ns | 369,284,375 ns |
| Software tail interval | 5,283,385 ns | 11,735,468 ns |
| Derived retained probe age at software tail end | 131,117,292 ns | 381,019,843 ns |

These are **different captures**; the old run has *no original host recorder-stop monotonic companion*. No historical monotonic value is inferred, and the new success does not prove why the prior host epoch moved backwards. The `last_pre_submit_probe_queue_count=0` value was obtained only at normal submit attempt #1425; it is **not a queue-depth query at shutdown**. Actual normal submit attempts at tail begin: #1437.

The new run's original guest software stop interval 11,735,468 ns is not a benchmark for physical DAC, actual acoustic fade, thread scheduler wake-up, or host-recorder SIGINT interval. Host clocks and guest clocks are not calibrated against each other.

## Stage363 archive replay scope

The independent Stage363 auditor in `tools/audit_nexium_stage363_authentic_guest_host_dual.py` validates **14 exact source SHA-256 pins** from the completed run, including both host recorder-stop CSVs, the original Stage362/303 reports, the actual 8.8MB host PCM recording, Stage313/351/348/357/360 source receipts, the original guest tail wait, lease, reason and pre-submit queue-probe CSVs. It uses the already independent Stage362 dual-clock auditor and guest Stage357/360 parsers and rejects mismatched original source receipts (including Python integer-for-boolean confusion). Only a compact JSON replay verdict is uploaded.

The strict Stage303 original source report must match the actual two stop snapshots, host wall delta, frame count, PCM SHA-256 and terminal-source conservation flag. The Stage362 report must match the original paired clock CSVs byte-for-byte in parsed meaning and SHA-256. Guest Stage357 and 360 receipts must match their own original source re-parses, with lease balance 1438/1438/0 and `audoutWait` software result 0.

The dedicated [Stage363 synthetic tests](../tests/test_audit_nexium_stage363_authentic_guest_host_dual.py) reject fake PCM growth, rewritten source receipts, false hardware provenance, missing guest-source origin paths, bool-vs-int receipt replacement, duplicate original files and symlink attacks. These tests are **not** a substitute for the real SHA-pinned workflow.

**Status:** source auditor, tests, and dedicated CI created in PR #176; success of Stage363's *own* workflow must be observed before claiming that particular independent replay passed. Original NeXium #39340120727 and Stage362 18-test host regression workflow have already passed.

No Nintendo Switch hardware speaker/DAC tests, retail PS1 soundtrack verification, new guest service calls, modifications to guest PCM, fade, 48-kHz path, or bounded 12-ms wait were introduced.
