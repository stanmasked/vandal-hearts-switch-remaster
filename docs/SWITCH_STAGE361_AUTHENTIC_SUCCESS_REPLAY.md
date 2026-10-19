# Stage361 — independent replay of authentic Stage360 success while Stage303 stays failed

The original [NeXium run #39333759265](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39333759265) was **FAILED overall**. Its *completed* Stage313, 348, 351, 357 and 360 guest-source audit steps separately succeeded. The later strict **Stage303 host recorder-stop** audit failed; a green source-replay job must **never** relabel the original emulator run green.

A new independent [Stage361 workflow](../.github/workflows/stage361-original-success-probe-replay.yml) downloads only the exact `nexium-runtime-evidence` artifact from run `39333759265`. The [source auditor](../tools/audit_nexium_stage361_original_success_probe.py) requires a unique regular non-symlink instance of each expected source, matches six raw guest/host CSV SHA-256 pins, re-audits the Stage313/348/351 original triple through the existing independent parser, rechecks Stage357 raw Result and Stage360 pre-submit-probe CSV against their original receipts, and emits an exclusive compact JSON verdict.

## What the authentic guest capture reports

| Property | Original observation |
| --- | ---: |
| Last normal submit attempts at tail | 1365 |
| Most recent retained pre-submit probe attempt | 1361 |
| Pre-submit query succeeded, previous queue count | yes, 0 (only at attempt 1361) |
| Probe journal overflow | 0 |
| Pre-submit timestamp age at tail begin | 125,833,907 ns |
| Software tail begin to end interval | 5,283,385 ns |
| Derived age of earlier probe at tail end | 131,117,292 ns |
| Stage351 software reason | 7 / return_confirmed |
| Stage357 raw `audoutWaitPlayFinish` Result | 0 |
| Stage348 software page acquire / release / abandoned | 1366 / 1366 / 0 |

The derived 131,117,292 ns value is **not** a new query, queue depth at shutdown, kernel wait duration, DAC timestamp or acoustic measurement. It is the earlier pre-submit timestamp's age at the tail's **software end tick**, using only already recorded clock values.

## Original strict host recorder failure is not erased

The same archive's `scene-recorder-stop.csv` shows `before_sigint` and `after_wait` both at 8,732,688 PCM bytes, but host wall-clock epoch **1,792,449,461,974 → 1,792,449,461,203 ms**, an apparent **−771 ms** regression. Original Stage303 therefore remains **FAILED / nonmonotonic host wall clock**. The forensic replay records this failure as an explicit `false` verdict for Stage303 validity and whole-run success. It does not infer a guest-audout failure or prove why the host epoch regressed.

The suite includes SHA/canonical-byte mutation cases for synthetic original data, including forged queue count, altered probe age, PCM growth, missing receipts, forged bools and a fabricated monotonic host stop. The original Stage360 recording came from an earlier NRO and is unchanged by this replay.

**Stage361 status:** submitted in Draft PR #176; its dedicated GitHub Actions result must be checked before calling this independent workflow itself passed. The earlier Stage358 authentic `0xEA01` archive lacks the Stage360 probe-age CSV. No causal paired success-versus-timeout interpretation is established.

No modifications to the audio worker, PCM ownership, 48-kHz timing, 96-frame fade or single 12-ms bounded wait.
