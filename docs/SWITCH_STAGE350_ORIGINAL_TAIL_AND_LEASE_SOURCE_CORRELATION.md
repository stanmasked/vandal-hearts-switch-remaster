# Vandal Hearts Remake — Stage350 original exit-tail and software lease cross-audit

## Original source evidence

After Stage349 independently reopened both original NeXium software lease CSVs successfully in [CI #39299969110](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39299969110), a separate review of the **same original NeXium runs** found a paired Stage313 exit-taper difference.

| NeXium original run | Stage313 bounded exit tail attempted | Stage313 tail descriptor return confirmed | Stage348 acquired / released / abandoned |
|---|---|---|---|
| [39292707481](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292707481) | yes | **no** | **1427 / 1426 / 1** |
| [39292997818](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292997818) | yes | **yes** | **1446 / 1446 / 0** |

The original audio-lease CSV SHA-256 values are `3a9d3e738330713a81be4bf507485613485053b79f9a86df1516b683c8795365` and `9e2724e77795fafd1374bc502cd3457c942190650ea34b9400fde33218f048db`. The independent original Stage314 guest last-buffer witness CSV hashes are `749a0ac0642c492bd29f7aaeda4ca13dfac8b46507cf2f84ed91c73234834f3b` and `59ac2224f5962547aa98ff7136a4fe77b8420fce5cdf413daab322c7057b4cdc`.

These are two distinct source cohorts. The first retained one lease until the **audout session was closed**, instead of confirming its exact descriptor return; the second confirmed a bounded tail descriptor return, and no lease remained unreturned at close. The source-paired observations **coincide**. They do **not prove** that a failed tail is the unique origin of an abandoned session, nor any audible dropout: concurrent/recovery events and the observed service return value are not uniquely attributed by existing counters.

## New independent Stage350 re-audit

`tools/audit_nexium_stage350_original_tail_vs_lease.py` independently reads **both original source pairs**, with four SHA-256 pins and each run's previously created:
- Stage313 original `audio-exit-output-000.csv` and `guest-last-audout-release-stage313.json`
- Stage314 `guest-original-audout-last-page-stage314.json`
- Stage348 original `audio-lease-reconciliation-000.csv` and `guest-lease-reconciliation-stage348.json`

The auditor checks exact source hashes, canonical ordered numeric fields and field-to-receipt equality, Stage313/314 original file preservation and source-only scope, Stage348 lease conservation, cross-run uniqueness and safe source file paths. Absolute guest/host timestamps are **not emitted** in its comparison report. No source file is modified.

The separately triggered [Stage350 workflow](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/stage350-original-exit-tail-lease-correlation.yml) first runs **17 synthetic negative/positive tests**, then downloads both previously successful original real NeXium evidence artifacts using GitHub Actions read-only permissions. Its second job separately reopens both original tail/lease files and demands the exact observed paired statuses. Do not report the new **independent Stage350** check as passed until its own second CI job is green.

## Scope and next decision

Stage350 is a source-only **post-run analysis**; no SPU, transport, audio-owner hot-loop, tail timeout, guest NRO, gameplay, private game assets or established Stage299–305/334/336 source formats are changed. 

A source-pinned two-cohort correlation is evidence that the *existing lease protection* behaved conservatively in these original captures, not direct evidence of which libnx/Horizon branch failed. If further attribution is needed, add a separate post-join *cause-classification witness* to the owner (e.g. tail append failure vs bounded-wait failure vs descriptor mismatch) and compare new genuine NeXium original source captures. Such instrumentation must remain bounded and nonblocking on the audio producer and must not change original CSVs or suppress errors.

No device queue drain, DAC/sample clock synchronization, speaker output, audible absence of glitches, original PS1 music fidelity or physical Nintendo Switch sound is verified.
