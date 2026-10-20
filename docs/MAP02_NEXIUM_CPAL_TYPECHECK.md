# MAP02 Stage275 — real Rust Cargo type-check of pinned CPAL/AudioOut overlay

**Draft / DO NOT MERGE.** Child of [Draft PR #286](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/286), immutable parent commit `1d666549d3fd99a2c0f557566880b6f7f852469d`. No Nintendo Switch game/audio production files, original PS1 game images, licensed PCM, or ancestor PR branches change.

## Prerequisite

Stage274 [Actions #39462977501](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39462977501) successfully verified 8/8 synthetic tests and applied an atomic-only callback + AudioOut metrics overlay to the **actual upstream NeXium source**, checked out at exactly `089562567a0a8760dfdd8420e1f57c35159a9219`. Source diff and checksums were validated for exactly three files. Rustfmt parsing passed. This was *not* a real Cargo type-check, build or runtime test.

The actual upstream has two host sink setup paths (ordinary CPAL output and `PullStream`). The Stage274 overlay was tightened to attach the periodic observer only at the ordinary CPAL initialization site.

## New proof obligation

The independent `map02-nexium-cpal-cargo-check.yml` workflow:
1. Checks out the exact research branch head and the fixed, immutable upstream NeXium Git SHA into **separate** workspaces. Rejects all changes except the new Stage275 workflow and this documentation.
2. Installs ordinary Linux ALSA/Clang/Opus dependencies, runs all eight ROM-free source overlay regression tests, and applies the exact Stage274 overlay. Verifies only the two Rust files and one runner Cargo manifest changed; verifies the source SHA/receipts.
3. Resolves Cargo dependencies, **records the new generated Cargo.lock SHA-256** (upstream has no committed lockfile at this revision), and runs `cargo check --locked -p nexium-runner --no-default-features`. This checks **real Rust types in the CPAL callbacks and the dependent kernel AudioOut handlers**, without invoking unrelated optional Dynarmic/Rustarmic CPU backends. It does not link or execute NeXium.
4. Publishes a positive type-check receipt **only after** the real Cargo command succeeds. CI uploads the source receipt, dependency lock digest and compiler log, including on failure. Missing data fails closed rather than making an unproven success claim.

The resolved dependency lock is a separate reproducibility variable; a successful compiler pass is valid for the recorded dependency snapshot, not an assertion of historic nightly binary equivalence.

## Honest limits

A successful Cargo check does **not** mean an instrumented NeXium Linux executable was built or booted. No guest `audoutPlayBuffer` result, CPAL callback trace, speaker output or causal explanation of the 21-ms issue is provided by this stage.

The subsequent experiment would build a new NeXium host executable from these pinned sources and re-run the controlled 21/22-ms paired tests with its *new* binary SHA-256, source receipt, guest NRO/CRC-8 and virtual PCM archive audit. Any change in Linux host audio behavior is a different experimental workload, not a repair of the production Switch audio system.

**No merge to main.**
