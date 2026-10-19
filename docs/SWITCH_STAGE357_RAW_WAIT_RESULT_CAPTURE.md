# Stage357 — capture the numeric audoutWaitPlayFinish Result from the existing bounded tail wait

The authenticated real NeXium [#39320606595](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39320606595) recorded a genuine **Stage351 4 / wait_failed** outcome and **1379 acquired / 1378 released / 1 abandoned** software descriptor. Stage351 classified a failing `audoutWaitPlayFinish`, but its eight-row original source contains **no numeric libnx Result**, so it cannot distinguish particular service errors.

Stage357 changes **only the existing one-time normal-exit tail diagnostic**. The audio worker stores the `uint32_t` bits of the Result **already returned** from the existing single `audoutWaitPlayFinish` call. It adds no extra audio service call, wait, polling, clock read, allocation or PCM operation. The existing 12 ms timeout, lease ownership, retry policy, SPU, music source, output format and eight-row Stage351 CSV remain unchanged.

After worker join, the main thread exclusively creates a **different guest CSV** `audio-exit-tail-wait-result-000.csv`, with canonical numerical fields `software_wait_result_only`, `wait_result_observed`, `audout_wait_result_raw` and `stage351_tail_reason_code`. A code 4 requires an observed **nonzero** raw Result. Codes 5, 6 and 7 require an observed zero Result. Prewait codes 0–3 must have **no** Result; invalid contradictory reports are rejected. Partial exports are deleted.

Host GCC/Clang/UBSan unit tests validate all classes of post-join report and malformed causal combinations. Actual code values and their relationship to a failing Horizon/NeXium service will only be known after a **new** NRO/NeXium guest source is captured and independently reaudited; this instrument cannot retroactively decode old Stage351 archives.

This new software Result is **not** proof of speaker sound, DAC playback, hardware Nintendo Switch audio or a root cause of the older unclassified failed runs.
