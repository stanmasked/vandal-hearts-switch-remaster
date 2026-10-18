# PR #7 — audio integration audit against the CDXA target branch

Status: **pre-merge review only**. This note does not declare a clean merge,
physical audio playback or a completed Nintendo Switch port.

## Pinned comparison

- Target: `test/cdxa-extract-decode-pipeline`.
- Feature: `feat/native-av-ps1-seq-integration` (PR #7).
- Last inspected merge base: `90b0ff1cb9ba310a52b2186bdea078496af8e53c`.
- GitHub three-dot comparison at the audit point reported 14 paths edited on
  both sides, 602+ commits ahead and 801 behind. Counts will change after
  further commits. **Two-sided edits are not automatically 14 text conflicts.**
- GitHub marked the PR not mergeable (`dirty`) at that point. Do not overwrite
  the target's current files wholesale with the feature versions.

## Paths requiring a three-way review

| Area | Both-sides-touched paths | Required check |
| --- | --- | --- |
| Playback service | `source/vh_audio_output_recovery.c`, `.h` | Retain target's existing submit/reopen contract and feature's lease, event counters, backpressure, page timing and resume APIs. Audit struct layouts and callers. |
| Musical sequencing | `source/vh_native_seq.c`, `.h` | Preserve target's read-only `vh_native_seq_audit` and feature's `vh_native_seq_switch_scene`; validate both with synthetic banks. |
| Native probe | `probes/audout_audio_smoke.c` | Keep target's ramp/scene integration and feature's strict exact-page return and fault diagnostics. |
| Build and CI | `Makefile`, `.github/workflows/host-audio-tests.yml`, `.github/workflows/switch-audout-nro.yml` | Preserve target tests and add the feature's jobs without deleting steps or duplicating incompatible targets. |
| Test fixtures | `tests/test_vh_audio_output_recovery.c`, `tests/test_vh_native_seq.c`, `tests/test_native_spu_reverb_reference.py`, `tests/test_native_vab_python_reference.py` | Bring both suites forward; keep callback-free PCM reference and negative service-failure tests. |
| Documentation | `README.md`, `docs/SWITCH_LOCAL_AUDIO_TEST.md` | Preserve both instructions and the distinction between simulated, emulated and physical playback. |

**Target-only components preserved without alteration:**
`source/vh_audio_output_ramp.c/.h` and `source/vh_music_scene.c/.h`,
plus their original `tests/test_vh_audio_output_ramp.c` and
`tests/test_vh_music_scene.c`, have been added to the feature branch.
All six GitHub blob hashes match the target branch byte-for-byte as
checked on 2026-10-18. A separate `target-audio-compat` CI job now
compiles both tests with UBSan; passing CI must be confirmed separately.
These components are intentionally not automatically wired into the
currently tested audout callback or scene-switch flow. The target's
fade-out director and the feature's wet-tail-preserving scene switch
have distinct ownership/transition policies, so reconcile their use
explicitly before changing production routing or Makefile targets.

## Work performed safely in the feature branch

The strict target-side SEQ preflight API (`VhSeqAudit`,
`vh_native_seq_audit`) was copied into the feature's header and
source alongside its scene-switch API, without rewriting target branch
history. A regression test now checks that preflight audit identifies
a missing note, does not publish an invalid report, and leaves
an active SEQ/SPU/ring unchanged. This is an initial compatibility
port only. Both APIs must still pass the full host and native CI on
the eventual integration branch.

## Cross-module synthetic playback bridge

Added `tests/test_vh_music_scene_resume_pipeline.c` and a separate ASan+
UBSan step in `target-audio-compat`. This checks one combined diagnostic
pipeline with two synthetic music cues, 64 render blocks, a three-block
fade between cues, a fade to silence and a new fade-in; each block passes
through 44.1-to-48-kHz resampling and the target-side 192-frame output
ramp before a bounded mock audout submission. A separate callback-free
reference processes the same cue sequence and compares every output
page, rate phase and cumulative checksum. The mock injects repeated
submit errors, then explicit quick-start and forced reopen events
(including an open failure). It also checks that recovery touches no
SEQ/SPU/rate state and delivers one logical PCM page exactly once.
A refused device stop during the third explicit resume must leave the
session open-but-stopped, must not call close/open/start or change recovery
counters, and must not submit any PCM until the next explicit attempt.
This failure is modelled in the host callback only, not on hardware.

This bridge is a **host-only synthetic integration regression**, not a
replacement for the real libnx producer or its ownership model. Do not
enable the director/ramp in the NRO until this new ASan/UBSan job passes
and the full service lifecycle and physical playback can be evaluated.
The mock `close` operation is intentionally idempotent to represent a
retry after `open` fails, matching native audout teardown semantics.

## Required integration gates

1. Create a disposable integration branch at the **current target HEAD**;
   do not force-push the target or merge PR #7 as-is.
2. Compare all 14 dual-touched files against the three-way merge base and
   resolve actual overlapping hunks; preserve target-only modules.
3. Compile and run target plus feature Host SPU, ASan/UBSan, SEQ audit,
   scene switching, source VAB resolution, resampler, exactly-once
   page replay, and bounded resume-failure tests.
4. Build libnx NROs; run all seven NeXium guest fixtures, downloaded
   evidence inventory and digest-binding verification.
5. Keep original user-owned game assets outside GitHub and CI. A passing
   emulator screenshot/digest check cannot certify audible music or
   physical Switch suspend/HOME behavior.
6. Only consider merging once no semantic or textual conflicts remain
   and the **new integration HEAD** has its own successful CI evidence.

All test artifacts and emulated events here are diagnostic; they do not
claim actual physical Switch playback or a signed attestation.
