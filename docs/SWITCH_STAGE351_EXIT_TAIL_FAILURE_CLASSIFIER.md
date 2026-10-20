# Vandal Hearts Remake — Stage351: original NeXium bounded exit-tail cause classifier

## Why Stage351

Stage349 independently re-opened two successfully archived real NeXium software lease sources in [CI #39299969110](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39299969110). The original [NeXium #39292707481](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292707481) reported 1427 acquired, 1426 returned, one session-abandoned descriptor; the original [#39292997818](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39292997818) reported 1446/1446/0. Earlier Stage313 original sources show that the former attempted a short exit taper without confirming return while the latter attempted and confirmed return.

Stage350 independently source-pairs both original Stage313/314/348 CSV sets, but **the concurrent count difference does not uniquely establish the failing audout service branch**. Stage351 is the narrow next software-only measurement, not a modification of playback.

## Production code and precise reason taxonomy

The original `output_tail_submit_bounded` runs once, if at all, only during normal audio worker cleanup. Stage351 instruments only that existing cleanup path with a worker-owned C11 atomic reason code and does **not** add timestamp queries, service calls, waits, allocations, filesystem I/O, queue polling or timing changes.

| Code | Original cleanup result | Lease status |
|---|---|---|
| 0 | No exit-tail call occurred | No exit-tail lease |
| 1 | Input/service precondition rejected | No newly acquired tail lease |
| 2 | Exact descriptor lease could not begin | No newly acquired tail lease |
| 3 | `audoutAppendAudioOutBuffer` returned failure | Retain lease until session closes |
| 4 | `audoutWaitPlayFinish` returned failure | Retain lease until session closes |
| 5 | Wait succeeded but returned zero buffers | Retain lease until session closes |
| 6 | Returned descriptor failed exact lease match | Retain lease until session closes |
| 7 | Exact descriptor was returned and released | Tail lease returned successfully |

Only one code is captured per execution. A failed call preserves the earlier error path and cleanup sequence. The wait timeout remains **12 ms**. A timeout or failure is a guest software-service result, not a measured audible dropout or speaker output.

## Distinct post-join guest evidence

The worker stores its final code in `VhAudioExitTailReason`; after the thread joins, the main thread creates a separate, exclusive `audio-exit-tail-reason-%03u.csv` file. The canonical eight-row `scope,value` source records the code, attempted/confirmed flags, whether the tail lease was acquired, and final acquired/released/abandoned owner totals. The writer refuses records inconsistent with the original Stage313 software exit-tail witness or Stage347 lease conservation. Failed partial exports are removed. Original Stage307, Stage313, Stage322, Stage347, Stage348, Stage299–305/334/336 files and strict tests are not changed.

`tools/audit_nexium_guest_tail_reason_stage351.py` independently reopens the original guest source path through the NeXium guest SD locator, rejects symlinked directories and ambiguous CSVs, validates exact ordered canonical rows, checks the Stage313/348 source receipts, and preserves the original CSV bytes with an independent SHA-256. The full `.github/workflows/emulator-smoke.yml` now demands the original Stage351 source to pass on a fresh NRO run; tests or a successful compile alone are never described as actual guest-source observations.

## Verified NeXium runs and failure forensics

[NeXium #39308380160](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39308380160) completed end-to-end with an **original guest software Stage351 code 7** (`return_confirmed`) and independent Stage348 counts **1441 acquired / 1441 released / 0 abandoned**. This is the *successful* bounded exit-tail branch, not an audible-quality assertion.

A second genuine [NeXium #39311305607](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39311305607) completed the NRO build and proved a different Stage348 guest software balance: **1468 acquired / 1467 released / 1 abandoned**. Its Stage351 audit was **not verified**: the strict auditor required the original Stage313 guest CSV preserved by Stage314, but Stage314 was positioned later in the workflow. The source dependency was not present; there is **no authenticated Stage351 reason code from this run**.

The workflow now enforces producer-before-consumer order: **Stage313 -> Stage348 -> Stage314 (copies original Stage313 CSV) -> Stage351**. A dedicated regression test checks the order and unchanged mandatory raw inputs. This fix changes CI orchestration only, not the audio worker.

### Fail-closed diagnostic quarantine

If and only if the **specific Stage351 audit step** fails, an optional forensic step attempts to copy at most **512 bytes** of printable original guest diagnostic CSV and an SHA-256 receipt under `stage351-unverified-quarantine.*`. Its GitHub Actions predicate is tied to `steps.stage351_audit.outcome == 'failure'`, not an unrelated earlier workflow failure. Symlinked paths, ambiguous sources, existing destinations, binary payloads and oversized input are rejected. No raw PCM/music bank is exported. This optional step **cannot convert failed CI to success or identify a reason code**.

The strict original source checker now emits a *nonsecret diagnostic phase* on failure — `destination-preflight`, `required-input-files`, `read-input-receipts`, `prior-original-source-reaudit`, `stage351-guest-source-reaudit` or `preserve-verified-source`. Each failure is marked `stage351_reason_code_validated: false`. These are failure locations in the host auditor, **not guest audout service errors**. Two original-source rejection regression tests and one precise-workflow-scope test guard the change.

The expanded strict-auditor and quarantine tests, and a fresh NRO run containing these later fixes, are not evidence of completion until their GitHub Actions jobs actually finish. The earlier real code-7 verification remains valid for its own original archived NRO only.

## CI and limitations

`.github/workflows/stage351-exit-tail-reason.yml` tests the source-only C11 writer on GCC and Clang both optimized and under UBSan, plus synthetic positive/negative Python audit and failure-only quarantine tests. Only CI that completes successfully may validate these new code paths. A separate successful, source-bound NeXium run is required before interpreting original numeric Stage351 reason codes.

Stage351 determines *which software branch returned failure during a bounded exit-tail attempt*. It does **not** prove that branch caused an acoustic problem, that a buffer reached a DAC or speaker, physical Nintendo Switch playback, or original PS1 soundtrack fidelity. Even a returned descriptor establishes software ownership only.
