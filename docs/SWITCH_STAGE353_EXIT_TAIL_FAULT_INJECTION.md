# Vandal Hearts Remake — Stage353 actual exit-tail decision-branch fault-injection coverage

## Background

The authenticated [real NeXium NRO #39308380160](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39308380160) completed successfully and its guest software Stage351 code **7** confirmed a returned tail descriptor. The original Stage348 software lease counters were 1441 acquired, 1441 released, zero abandoned. Older real NeXium source cohorts had one abandoned lease during an unconfirmed bounded exit tail, but those old runs had no Stage351 reason discriminator.

Until a *new real failed-return* NeXium capture occurs, the failing append/wait/empty/mismatched-service branch of the older instance is **unknown**.

## Stage353 production-shared fail-closed decision logic

`source/vh_audio_exit_tail_checks_stage353.h` introduces two pure C11 helpers used from `output_tail_submit_bounded` in the production Nintendo Switch audout worker:

- `vh_audio_tail_stage353_append_checked` classifies **the single actual** `audoutAppendAudioOutBuffer` result. An error retains ownership of the single borrowed PCM descriptor until whole-session closure.
- `vh_audio_tail_stage353_wait_checked` classifies **the single actual** bounded `audoutWaitPlayFinish` return, distinguishing service error, zero buffers, foreign/null descriptor and exact lease return. No descriptor is released except through the **existing** `vh_audio_buffer_lease_release` exact-token check.

The original submission/service call count, buffer alignment and size, 12ms maximum wait, owner-only context, exit marker, restart policy, PCM contents and game/music clocks are unchanged. No hot-loop, extra service operation, additional clock read or filesystem access was added. Old software-source CSVs and independent Stage351 reason code schema stay unchanged.

## Host injection

`tests/test_vh_audio_exit_tail_stage353_fault_injection.c` drives those very same production-shared decision helpers against actual `source/vh_audio_buffer_lease.c` lease logic in an isolated C11 harness. It verifies exactly one mocked append and one mocked wait (wait skipped after append failure), and tests:

- append failed -> Stage351 reason 3, lease retained
- wait failed (even if an output pointer is supplied) -> reason 4, lease retained
- wait empty -> reason 5, lease retained
- foreign or NULL released descriptor -> reason 6, lease retained and mismatch recorded
- matching descriptor and nonzero count -> reason 7, lease released
- multiple released count is **not** used to fake correct descriptor ownership; returned pointer must still match
- after every unresolved ownership result, another begin is denied, stop alone cannot release, and only full session close allows safe reuse

The [independent Stage353 workflow](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/stage353-exit-tail-fault-injection.yml) compiles/runs the C11 harness with GCC and Clang both optimized and under UBSan. The workflow is not complete until its GitHub Actions checks actually report success.

## Evidence scope

Fault-injection harness results are *synthetic*, not observed Horizon/libnx service failures. They do not reproduce the older NeXium failure code, confirm actual speaker output, DAC queue drain, hardware Nintendo Switch sound or PS1 soundtrack accuracy. The only genuine Stage351 branch observed in a completed NeXium capture so far is **7 / return_confirmed**.
