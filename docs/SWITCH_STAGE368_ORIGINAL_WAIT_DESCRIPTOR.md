# Stage368 — original audoutWait released-descriptor tuple, no extra service call

## Objective and original-source limit

The authentic older [NeXium #39325440778](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39325440778)
returned `0xEA01` from its bounded tail wait and had software lease
counts `1414/1413/1`. The separate success [#39340120727](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39340120727)
returned zero with `1438/1438/0`. Stage365 independently reaudited
both archives but **the older failed run has no Stage360 queue probe**.
Do not infer its queue size, physical playback or kernel subcall.

Stage357 recorded only the service `Result`. Stage368 adds a *separate*
bounded one-shot software witness capturing these values already
returned from the **same original** `audoutWaitPlayFinish` invocation:

- raw `Result` and the reported `released_count`;
- whether the returned descriptor pointer is non-null;
- whether that pointer equals the descriptor already submitted by the
  audio owner.

No pointer address is serialized. A returned pointer is only a
software descriptor observation; it does not establish DAC playback,
audible output or precise queue depth.

## Unchanged release behavior

The existing single `audoutWaitPlayFinish(..., 12000000)` call remains
unchanged; no extra service query, wait, clock query or memory allocation
occurs in this recording. Stage353 still makes the ownership decision
and Stage368 records only afterwards without changing its return.
If a wait fails, no lease is released; `audoutExit` still invalidates
the outstanding old-session descriptor. PCM, 48-kHz output and the
96-frame fade remain unchanged.

A new `VhAudioExitWaitDescriptor368` witness is reset at audio startup
and written by the single worker. A post-join-only CSV
`audio-exit-wait-descriptor-NNN.csv` uses an exclusive new file, exactly
eight numeric rows after `scope,value`, without rewriting the
original Stage313/347/351/357/360 evidence.

The CSV writer rejects inconsistent original Stage351 tail reasons,
Stage357 raw wait results, unobserved waits falsely classified as
success, a claimed successful release with a missing/mismatched
descriptor, and impossible absent/present pointer flags. A failed
service wait may still report an uninterpretable count or pointer;
the witness preserves it **without** using it to release ownership.

## Verification boundaries

[Stage368 workflow](../.github/workflows/stage368-original-wait-descriptor.yml)
runs GCC/Clang C11 optimized and UBSan synthetic controls plus Python
source integration checks that require exactly one original 12-ms wait,
a new exclusive post-join CSV and no extra audout/clock calls.

The companion `tools/audit_nexium_stage368_wait_descriptor.py` is a
**source-format validator for future captures**, not a NeXium attestor:
it requires exact ordered Stage351/357/368 CSV rows, matches their
software result and release counts, rejects ambiguous duplicates,
symlinks, mixed directories and false descriptor-return claims, and
reports SHA-256 for all three input files. It explicitly outputs
`original_neXium_archive_proven=false` until a new workflow independently
proves the original capture's source/run identity.

The related negative-control tests execute in the Stage368 workflow.

### Integrated original NeXium capture path

The existing [emulator-smoke workflow](../.github/workflows/emulator-smoke.yml)
now executes a separate Stage368 audit **after** the established Stage351
and Stage357 original guest source verifications. The wrapper
`tools/audit_nexium_stage368_attested_guest.py` requires:

- A single isolated NeXium SD root tied to this **same** GitHub run;
- The current NRO preflight's exact Git SHA, run ID, attempt and NRO SHA;
- Previously independently verified and byte-preserved original
  Stage351 and Stage357 CSV receipts;
- Exact SHA-256 identity of the original Stage351/357 files in the
  same directory as the newly added Stage368 descriptor source;
- Strict Stage368 canonical row ordering, software release-count
  consistency, and raw Result agreement with Stage357.

Only a verified current-run source emits
`STAGE368_SAME_RUN_ORIGINAL_GUEST_WAIT_DESCRIPTOR_BOUND_TO_351_357_NRO`.
The new original CSV is copied byte-for-byte to
`runtime-evidence/audio-exit-wait-descriptor-000.csv`, and the
source-bound JSON receipt contains all three SHA-256 digests. Both
are preserved by the pre-existing runtime evidence artifact upload.
The wrapper's six adversarial tests reject forged prior receipt
digests, swapped original bytes, wrong NRO source/run/attempt and
false kernel-timeout causal claims.

The [integrated runtime run #39388027581](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39388027581)
was queued at the time this capture path was added. This is therefore
**an implemented verification path, not yet a proven genuine new
NeXium observation**. If its earlier mandatory host recorder or guest
source auditors fail, Stage368 must not be promoted to verified.


The new schema is **not proof of a real captured `0xEA01` run**.
Independent NeXium evidence from a newly built NRO must still establish
whether a real timed-out tail returns zero or nonzero descriptors and
how those outcomes differ between actual captures. Synthetic native
tests alone cannot explain the old timeout or verify physical speakers.
