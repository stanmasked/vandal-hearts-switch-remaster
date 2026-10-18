# Vandal Hearts: audio-to-main integration prerequisites

This document records an **integration blocker**, not approval to merge.

The current repository has parallel development histories: `main` carries graphics/MAP02 work, while `test/cdxa-extract-decode-pipeline` carries the Switch audio foundation. Stacked Draft PR #171 (`59392c1e`) depends on that foundation; Draft PR #177 (`bb92f521`) adds experimental STUDIO_C wet-tail continuity on top. Draft rehearsal PR #187 verified this stack *against the audio branch*, not against `main`.

Do **not** cherry-pick PR #171 or PR #177 directly into `main` without their dependencies. The current `main` does not contain several foundational source files, including `source/vh_native_seq.c`, `source/vh_native_spu.c`, `source/vh_spu_reverb.c`, `source/vh_music_scene.c`, and `source/vh_switch_game_audio.c`.

## Reproducible, fail-closed preflight

The stdlib-only `tools/audit_audio_branch_lineage.py` compares two *actual Git refs* using read-only Git commands. Its JSON report records the exact SHAs, merge base, ahead/behind counts, source-file sets, ten required audio foundation modules and missing paths. It reads no original ROM/ISO or music assets.

Usage from a clone containing both histories:

```bash
python3 tools/audit_audio_branch_lineage.py \
  --destination refs/remotes/origin/main \
  --audio refs/remotes/origin/test/cdxa-extract-decode-pipeline \
  --output build/audio-main-branch-prerequisites.json
```

The expected current status is `BLOCKED_DESTINATION_MISSING_AUDIO_FOUNDATION` (normal CLI exit code 4). The separate CI workflow uses `--expect-status` to explicitly verify this **known blocker**, and tests its fail-closed behavior on six synthetic Git fixtures. A **green inventory CI check does not mean the integration is safe**. A change in the expected status requires re-review of the integration plan.

The JSON always reports `safe_to_merge_asserted: false`, `git_merge_tested: false` and `physical_switch_audio_tested: false`. Even `READY_FOR_REVIEW_NOT_MERGE_APPROVAL` is no substitute for a source merge, compilation or compatibility review.

## Required integration steps

1. Keep parent PR #171 and child PR #177 stacked and separate. Do not merge rehearsal PR #187.
2. Create a separate `main`-based integration candidate preserving current graphics and MAP02. Audit and port the required audio foundation first; never replace `source/main.c` or the `Makefile` wholesale from the parallel branch.
3. Review actual merge conflicts, resolve renderer/audio overlap intentionally, and run a fresh matrix covering graphics/MAP02 regressions, native audio GCC/Clang sanitizers, tactical NRO, virtual graphics/audio/scene tests, and any target-specific checks.
4. Record external failures distinctly: optional SDL2 integration still fails at an HTTP 403 from the devkitPro package mirror, **before compilation**.
5. Treat NeXium virtual PCM as emulator evidence only. Independent captures are not sample-aligned and cannot establish causal STUDIO_C reverb or physical Nintendo Switch sound.

This preflight intentionally adds no gameplay changes, copyrighted resources or production audio modifications.
