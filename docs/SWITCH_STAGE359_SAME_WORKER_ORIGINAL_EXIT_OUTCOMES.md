# Stage359 — compare real successful and timed-out tails on identical audio worker source

## Authentic original executions

- [NeXium #39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778), NRO commit `3ecf5933d913b449148edd510f21e7bde7af4e90`: original Stage351 **4 / wait_failed**, Stage357 **59905 / 0xEA01 = KernelError_TimedOut**, Stage348 **1414/1413/1**.
- [NeXium #39326719578](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39326719578), NRO commit `95b40a11d4dd98bbbe8c0f73e11486d7dd57ef69`: original Stage351 **7 / return_confirmed**, Stage357 **0 / success**, Stage348 **1366/1366/0**.

**Crucial invariant:** GitHub confirms both ORIGINAL commits have the **same source blob** for `source/vh_switch_game_audio.c`: `12c02352ac8b34e6357e68cac31e20e9a4630520`. Therefore the very same single `audoutWaitPlayFinish` call used a 12,000,000 ns (12 ms) timeout in both original runs. The Stage359 CI separately checks these git trees by commit SHA rather than trusting a comment.

## New independent comparison

Stage359 downloads the original two `nexium-runtime-evidence` archives, source-pins their four separate **Stage313, Stage348, Stage351, Stage357 guest CSVs**, and reaudits the Stage313/314/348/351/357 receipts via the strict original Stage352 and Stage357 validators. It requires different authentic original SHA hashes, checks the code4+59905 failure against code7+0 success, validates both independent lease counts, and emits one small JSON comparison. It derives the successful run's monotonic guest exit-tail attempt-to-return timestamp interval from original Stage313 data, **without inventing the failed run's unrecorded return timestamp**.

The fourteen synthetic counterexample tests reject alternative source blobs, forged Result/status, mistaken lease counters, duplicate hashes, missing success timestamps, invented failed-return timestamp and false physical playback claims.

**This is a same-source observational comparison, not a matched randomized experiment.** Runs differ in number of pages, potentially in queue depth, emulator scheduling and other uncontrolled timing. The source data cannot establish which of those differences caused KernelError_TimedOut, does not measure DAC/speaker playback, and does not prove audible discontinuity or real physical Nintendo Switch output. No production wait, buffer release policy, PCM rendering, original game resources or soundtrack was changed.

## What would establish the next causal step?

Collect matched queue-state traces at the **start** of the existing bounded exit-tail wait (without adding blocking calls in the audio worker), compare source-verified run cohorts, and only then consider controlled variations. The 12-ms production bound remains our untouched baseline. Do not claim Stage359 successful until the GitHub Actions replay completes.
