# Main/MAP02 + native audio foundation: first non-disruptive staging

This PR is a **main-based integration candidate**, NOT a complete integration of the
audio engine into the tactical game's render/update loop. Its code is not used by
`source/main.c` yet. It must stay Draft until C tests, MAP02 tests and provenance
checks have been reviewed.

## Exact content

- Base: `main` at `af8e1709488df6e9bcc591e66fae337bcf713c69`.
- Audio source: validated combined stack `bb92f521596588ab47e2e529fc8a3ebacb5a93a8`.
- 50 previously absent `source/vh_*.c/.h` files copied as **unchanged Git blobs**
  from the audio source stack, including SPU, SEQ, STUDIO_C reverb, music director,
  game music bank/mailbox, diagnostics and native audout bridge.
- Eight corresponding audio C regression sources also copied as unchanged blobs.
- Only additions to CI and docs and a standalone host test script, without changing
  the original `Makefile`, `source/main.c`, graphics/MAP02 headers or existing
  tests. Original `source/vh_native_tone.h` stays owned by `main`.
- No original Vandal Hearts PS1 disc/ROM, proprietary SEQ/VAB resources, or recorded
  copyrighted sound files are imported.

## What this stage tests

`.github/workflows/main-map02-audio-staging.yml` runs:

1. Seven original `main` graphics / MAP02 host C tests (no audio overrides).
2. Eight audio test programs under both GCC and Clang with ASan+UBSan:
   stream, resampler, native SEQ, SPU reverb, native SPU, native VAB,
   scene director, and 48-kHz music-scene soak.
3. Git blob identity for **all 50 source and 8 test files** against exact combined
   audio head. A separate diff gate checks that `main`, its `Makefile` and key
   renderer/MAP02 files retain their original contents.

The separate preflight [#193](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/193)
demonstrated why simply merging parent audio [#171](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/171)
and child [#177](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/177)
directly to `main` is unsafe: the required foundations were previously absent
and the histories diverged significantly.

## Explicit exclusions and next engineering gates

This does **not** wire audio into `main.c`, modify the platform loop, or produce
a combined MAP02+music NRO. The source files are present and can be tested
independently, but a full link/integration may encounter overlapping game state,
platform-input, graphics or build-target contracts.

Before wiring in production audio:

- audit the MAP02 game's frame scheduler and the audio branch's audout worker
  lifecycle; design an additive integration preserving both systems;
- add a main-based composite build target with stable inputs and verify both
  renderer and audio compilers, without replacing existing Makefile rules;
- re-run graphical NeXium/MAP02 regression and musical scene NeXium tests on the
  **combined** binary, not only independent build artifacts;
- treat devkitPro `switch-sdl2` mirror HTTP 403 as external CI failure; don't
  claim SDL2 build success;
- perform hardware speaker/DAC validation separately. Virtual host PCM A/B
  captures are not sample-aligned and do not prove the STUDIO_C effect causally.

**Do not merge this PR automatically**. Verify test outcomes and integration
boundaries and keep all prior audio PRs #171/#177/#187 unchanged.
