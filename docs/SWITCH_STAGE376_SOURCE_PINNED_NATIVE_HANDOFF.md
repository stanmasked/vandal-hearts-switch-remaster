# Stage376 — independent original-source audit for the native Switch NRO handoff

Stage375 produced a **private** handoff archive for the integrated tactical/audio Nintendo Switch homebrew NRO. This Stage376 addition checks the **public original CI provenance** independently; it does **not** upload any user-owned game images, extracts or commercial soundtrack to GitHub.

## Pinned successful build and prior gate results

- Original integrated tactical build: [GitHub Actions #39453952599](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39453952599), source head `7df0d02c93217b6f077e6ba30de9e1a554d95b9a`.
- Original artifact: [#12278869762](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39453952599/artifacts/12278869762), ZIP SHA-256 `cfc6ce877d238850d1d72c735f390e6a55c0729f4da72dade344af11f8c9ef97`.
- Native NRO: 299,064 bytes, SHA-256 `cfc49a8ac8dcfe4704e697c1bea8fc750ea32d498c2942176c2ca9b9cbcae71b`, `NRO0` header with 3 bounded segments.
- Separate completed source-head workflows: native `audout` #39453952461, native PCM #39453952443, host SPU #39453952411, eight-original-session Stage374 archive replay #39453952772.
- Separate optional SDL2 job **FAILED** in #39453952566 due to external mirror HTTP 403. This is not downgraded to a pass.

**This is a source-pinned historical candidate once the Stage376 commit is made.** Do not call it the NRO for a new HEAD merely because the current source changes are only tests/documentation. The NRO hash and run identity belong to the pinned original source head above.

## Stage376 gate

The dedicated [workflow](../.github/workflows/stage376-source-pinned-native-handoff.yml) downloads the actual original GitHub Actions **ZIP** and fresh live metadata, rather than trusting an uncorroborated name or SHA file inside the ZIP. The stdlib-only [auditor](../tools/audit_stage376_native_handoff.py) requires the independently pinned ZIP SHA-256, original run/head/attempt, successful integrated build job, source artifact identity and digest, two exact NRO/hash members, full NRO SHA and bounded header/segments, and separately completed successful native workflows. It also requires and reports the actual still-red optional SDL2 status.

Synthetic [tests](../tests/test_audit_stage376_native_handoff.py) cover corrupted and truncated NRO, overlapping segments, substituted archive hash, duplicate ZIP member, source run substitution, missing native job, incomplete workflow, symlink source and misleading SDL2 "green" data. Synthetic evidence never counts as a guest or device test.

The only file published by the Stage376 workflow is a compact JSON attestation containing hashes and provenance, **not** the NRO, commercial assets or guest PCM. If GitHub changes or archives expire, the checker **fails closed**, not backfills a result from local records.

## Evidence boundary and actual next steps

- `STAGE376_PINNED_INTEGRATED_NRO_BYTES_AND_NATIVE_CI_PROVENANCE_VERIFIED` means **existing native build + original source and supporting CI** are consistent. It is **not** a full green PR, final remake release or hardware qualification.
- Last original guest Stage371 completed two runs with matching software descriptors, but there is no test of physical Nintendo Switch speakers, DAC, HOME/sleep or real SD writes; `HARDWARE NOT TESTED` remains.
- Use the offline Stage375 private handoff and the existing [Stage239 physical test protocol](SWITCH_AUDIO_STAGE239_INTEGRATED_NRO_DEVICE_HANDOFF.md) to transfer the NRO **only once the user's Mac SD is connected**. Recompute SHA on the actual SD after copying. Do not assume file paths named `sdmc` prove hardware access.
- If the user changes hardware or any asset, re-attest the exact NRO and source rather than altering the original guest receipts.