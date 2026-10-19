# MAP02: synchronized STUDIO_C reverb continuity test

**Research only — Draft / DO NOT MERGE.** This test-only child of [PR #198](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/198) adds no changes to the actual MAP02 renderer, input engine, `source/main.c`, audout worker, default `Makefile`, or original game assets. Its parent had already demonstrated a **controlled** video-only silent null-sink recording versus an audio-enabled nonzero null-sink recording; that contrast did **not** by itself isolate reverb.

## Exact-clock host regression

`tests/test_map02_synchronized_wet_tail.c` instantiates two fully independent native SPU/SEQ/music directors with identical generated 128-frame PCM, pQES music cues, interpolation, reverb depth and A-button MAP02 input contract. Their only intentional difference is director option `keep_reverb_across_cues`: reset=0 (default/legacy) versus retained=1 (opt-in STUDIO_C).

1. Both play precisely 64 blocks (512 stereo frames per block) of the same field cue. The test asserts **bit-for-bit identical PCM on every block**, identical reverb state and note count.
2. One game-state A-button selection changes the scene to a valid **no-note** pQES hero-selected cue. Both directors switch on the same block boundary.
3. The new cue cannot add a dry voice or resolver note. Each director produces 48 subsequent blocks in strict lockstep. The test requires the reset variant's output to be **exactly zero** on every sample; retained-tail output to contain nonzero samples and differ from reset in at least one block; and both SEQ clocks, event counts and director phases to remain matched.
4. Both receive explicit silence. The test demands zero PCM and a zeroed reverb work buffer from both, preserving the security/ownership distinction between scene-switch continuity and teardown.
5. The whole test is repeated from a fresh synthesis state; initial, retained and reset PCM fingerprints, nonzero sample totals and block divergences must reproduce identically.

This test uses no PS1 music data. Its synthetic note is not original Vandal Hearts music, and its comparison is an isolated host-DSP causal test **only for reverb-state preservation at a common cue boundary**. It is not a hardware test or proof of musical fidelity.

## Coupled Switch binary provenance

`.github/workflows/map02-synchronized-wet-tail.yml` builds a separate MAP02+audio NRO with `VH_GAME_AUDIO_WET_TAIL=0` and another with `=1`, using two distinct build directories. Both reuse exactly the same game source and opt-in audio runtime. The NRO0 structural checker is required on both. The CI records exact Git SHA, run ID, attempt and SHA-256 of each executable and requires different hashes.

Cross-compile success does **not** imply that both NROs have been compared on Switch hardware or with guest sample-aligned NeXium captures. The compiled pair is saved for future runtime testing.

CI also executes the synchronized, generated-source host regression under **both GCC and Clang with ASan+UBSan** and retains each run's fingerprints. The existing parent [PR #196](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/196) remains unchanged.

**Integration:** keep this PR and its parents #194, #196, #198 Draft. Do not merge to `main` from an isolated research experiment.
