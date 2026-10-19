# Vandal Hearts Remake — Stage349 two authentic NeXium guest lease cohorts

## Why this is needed

Stage346 compiled and ran the active audio transport without retrieving the new in-game owner counters. Stage347 wrote a distinct software-owner CSV **after the worker joined**. Stage348 source-validated this guest-created file in two fresh, fully successful NeXium NRO workflows. Stage349 compares their exact archived original bytes, rather than comparing hand-entered or re-created CSVs.

The two source runs must be treated separately from synthetic tests:

| Original NeXium source | Source SHA-256 of guest CSV | Acquired | Released | Abandoned sessions |
|---|---|---:|---:|---:|
| [39292707481](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292707481) | `3a9d3e738330713a81be4bf507485613485053b79f9a86df1516b683c8795365` | 1427 | 1426 | 1 |
| [39292997818](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292997818) | `9e2724e77795fafd1374bc502cd3457c942190650ea34b9400fde33218f048db` | 1446 | 1446 | 0 |

These SHA-256 hashes and counts were printed by the original successful real NeXium runner logs during Stage348's original source receipt check, not invented by Stage349.

## Independent Stage349 replay

`tools/compare_nexium_stage349_original_lease_cohorts.py` accepts the **exact original, archived** `audio-lease-reconciliation-000.csv` bytes from each successful NeXium run, each run's previously generated Stage348 `guest-lease-reconciliation-stage348.json`, and the two original CSV SHA-256 pins. For each cohort it:

1. Validates its original SHA-256 pin, refuses a symlinked original CSV or receipt, and rejects a malformed/ambiguous canonical eight-row guest source using the independent Stage348 parser.
2. Rechecks every software counter and the source hash against the **separately archived, previously produced** Stage348 receipt. Rejects forged hardware-playback claims and non-source-only scope.
3. Rejects the same source used for both cohorts, invalid/repeated run IDs, unbalanced ownership, and report overwrites.
4. Emits only an independently derived, source-only Stage349 JSON comparison and per-field second-minus-first differences.

`tests/test_compare_nexium_stage349_original_lease_cohorts.py` has **17 synthetic positive/negative tests**, deliberately distinct from an original-run replay. The workflow `.github/workflows/stage349-original-lease-cohorts.yml` runs those tests first; its second job uses read-only GitHub Actions artifact download to re-open the two real archived sources and recheck both original Stage348 receipts. It pins the two original CSV SHA-256 values and their recorded acquired/released/abandoned counts. Only a **successful second job** supports the claim that Stage349 independently revalidated both originals.

## Scope and interpretation

The first NeXium run recorded one completed-session abandonment, the second zero. Both satisfy `acquired = released + abandoned_sessions`, with the prior Stage348 check ensuring `accepted_pages_submitted <= released`. This is a difference in the software-owned descriptor lifecycle, not proof of lost PCM samples at the device or a defect in audio output. Without original device or hardware source data, Stage349 **cannot explain the origin** of the one abandoned session or equate it to an audible dropout.

No source music, PCM payload, pointers, absolute software/host clock values or private game assets are published by Stage349. No SPU synthesis, guest PCM scheduling, audout calls, worker timing, NRO scene transitions, old Stage299–305/334/336 CSV formats, or strict historical validators are modified. Physical Nintendo Switch audio, DAC timing, original PS1 soundtrack fidelity and speaker output remain untested.
