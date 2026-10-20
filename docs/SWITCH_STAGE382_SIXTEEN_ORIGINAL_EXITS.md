# Stage382 — sixteen original NeXium guest audio-exit observations

This read-only audit extends the successfully completed source-bound **Stage378** twelve-session replay with two additional original Stage371 source runs (four independently captured NeXium guest exits). No new guest run is created by Stage382.

The new, immutable GitHub source bindings are:

| Source run | Head commit | Merge commit | Guest artifact | Original artifact ZIP SHA-256 |
|---|---|---|---|---|
| [39466729315](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39466729315) | `8b3c8a6df47ded9b597166806ffa65083c947134` | `1f361b89ccbfa50f85c0ea932f6a81e19fcecfba` | `12286756628` | `e21ea3b31f4ce3b46bd078886b84308f0c228a20e95c2778fe61927558253eec` |
| [39476667373](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39476667373) | `93230691ba184888ead11c8d18657212a946e63e` | `83d0252ec61274acb070bae74e49394992f44f4c` | `12289084323` | `4d271269be02f425614fc1beb2ceeaa225c80dece6b89f16d9424daad8bbc995` |

All eight source runs share one verified native Nintendo Switch NRO hash: `cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b`. Original run, job, PR-merge parent, artifact, guest-manifest and per-file SHA-256 checks are executed using the existing Stage373/374/378 stdlib decoder. The exact original 1280×720 PNG pixel payload and CRC checks must be read and decoded, not trusted from an unverified summary.

**Important legitimate repetition:** two distinct original sessions ([run 39462294094, trial b](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39462294094) and [run 39466729315, trial b](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39466729315)) produced the **same numeric counter CSV bytes**, including `2676` acquired and `2676` released PCM pages. Their original PNGs, CRC-checked decoded optical packets, run identities and guest roots are different. Stage382 therefore permits repeated content in reason CSVs *only while each CSV remains independently bound to its own original pinned source metadata*; it requires 16 distinct original PNG and optical packet hashes. Treating all 16 counter CSVs as necessarily unique would incorrectly reject valid data.

Positive results require 16 software `audoutWaitPlayFinish` results `0`, 16 matching returned descriptors, lease totals balanced per guest, 4 complete transitions and 23 optical events per guest (64 transitions in aggregate), zero dropped events, and internally coherent exit-tail guest clocks below 12 ms. The reported interval includes the tail append and bounded wait; it is not a pure kernel wait-duration measurement. Guest dwell times of 6 vs 12 seconds have no demonstrated causal effect. The original historical `0xEA01` cause remains unresolved.

**Boundaries:** this is a replay of archived NeXium original guest software evidence, not a physical Nintendo Switch run, not a speaker/DAC measurement, not a check of HOME/sleep on hardware and not original soundtrack validation. No ROM, SEQ, VH/VB, sound samples or commercial game assets are uploaded by this workflow. Hardware remains **HARDWARE NOT TESTED**. The existing 12-ms bounded wait and PCM ownership logic are unchanged.
