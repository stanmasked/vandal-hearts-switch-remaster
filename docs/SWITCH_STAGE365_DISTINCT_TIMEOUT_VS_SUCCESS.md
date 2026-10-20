# Stage365 — authentic timeout and success are distinct, non-causal evidence cohorts

## Source runs

Stage365 separately replays **two different actual archived NeXium executions**, using the existing Stage358 and Stage364 SHA-pinned original guest/host source verifiers.

| Source | Earlier timeout | Later successful audio exit |
| --- | --- | --- |
| NeXium run | [#39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778) | [#39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727) |
| Original Stage357 `audoutWait` raw Result | 59905 = `0xEA01` | 0 |
| Original Stage351 tail reason | 4 (`wait_failed`) | 7 (`return_confirmed`) |
| Software audio page acquire/release/abandoned | 1414 / 1413 / 1 | 1438 / 1438 / 0 |
| Stage360 old periodic queue probe at tail | **not recorded** | last prior probe at attempt 1425 |
| Stage360 old-probe age at tail begin | **unknown** | 369,284,375 ns |
| Direct queue depth at shutdown | **not recorded** | **not recorded** |
| Host paired SIGINT clocks | not jointly reaudited in this cohort | +21ms wall, +20,788,687ns monotonic |

The `0xEA01` original result decodes to Kernel module 1 / description 117 (`KernelError_TimedOut`). This does **not** uniquely establish the underlying kernel event-wait call site or explain why the old guest retained one software PCM lease. The new successful run is not an equivalent timed queue-depth sample from the old timeout.

## Independent verification boundary

`tools/audit_nexium_stage365_distinct_timeout_success.py` rejects duplicated, symlinked or changed original timeout sources, recalculates Stage313/348/351 original guest CSV and receipt proofs and verifies Stage357 from its pinned raw bytes using Stage358. It **requires absence** of the Stage360 probe-context source and receipt in the timeout archive, and represents unknown older queue depth and probe age as **null**, never zero.

As a second provenance barrier, Stage365 now also **SHA-256 pins all five original timeout JSON guest receipts**, rather than accepting receipt counters from a different historical execution: Stage313 `ca3a1727c03e400d594c3246863bff7c391805219c1d2d7e875a8ca9ab0ec2ac`, Stage314 `c648fcc360e9c36aeb0164e92d3c1abeba4ebc5a7be6f397c545e47c04bcf1fe`, Stage348 `5858aeb3bac7ac2ce9040032f7e56172338e3d0acb85dbab9244ac1cfcf55469`, Stage351 `2b94dba79b35fb8d464988242a862dee4da5fa0ac1b6dfab4daa7fa65a843b63`, and Stage357 `862a0ca78fb570dfc2502119eb2010e8a6b3eb90efdbf5e693a48c49cc90505a`. These are the exact stored original ZIP bytes of NeXium #39325440778, independent of the successful run's receipts.

It then independently reruns Stage364 against the *different successful archive*, verifying original Stage313/314/348/351 and successful Stage357/360, host Stage303/362 dual clocks, actual PCM SHA and source receipts. Cross-cohort validation preserves the exact original run IDs, SHA-256 source identities, exit codes, page-lease counters and explicit refusal to assert causal relationships.

The separate [Stage365 workflow](../.github/workflows/stage365-compare-authentic-timeout-success.yml) downloads both exact original artifact runs and requires successful independent replay before writing a compact JSON verdict. Its **23 synthetic mutation tests** cover forged timeout return codes, wrong run IDs, source SHA substitutions, falsely reconciled PCM pages, fabricated matched queue probes, physical-audio assertions, reported shutdown queue readings and clock alignment. Synthetic tests cannot replace real archived guest evidence.

No game code, libnx audio service operations, PCM samples, 48-kHz fade, 96-frame tail, ownership policy or bounded 12-ms wait were modified.

**Status:** The first Stage365 workflow failed its canonical-positive test because its strict field typecheck mistakenly used `guest_abandoned_sessions` instead of the genuine `guest_audio_abandoned_sessions`. This comparator defect was corrected without changing guest code or original evidence; two regression cases now require the correct field and reject a boolean disguised as numeric zero. The corrected 23-test workflow **passed** in [GitHub Actions #39351366143](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39351366143) on commit `2ddc2ab0` (23/23 tests). The independent report was retained as GitHub artifact `12233871696`. This proves separate reauditing of two original captures, not the cause of the older timeout.

**Status:** Stage364 has independently passed [GitHub Actions #39348708577](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39348708577) with 22/22 regression tests and original-archive reauditing. Stage365's independent authentic-archive workflow has now passed as described above. No origin of the earlier -771ms host wall-clock regression or old kernel-timeout cause is established here.
