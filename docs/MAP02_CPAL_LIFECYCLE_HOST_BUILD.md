# MAP02 Stage287 — compile a real lifecycle-instrumented NeXium Linux executable

**Research-only Draft / DO NOT MERGE.** This is an isolated child of [Stage286 Draft PR #337](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/337), at frozen head `07532b425f15b08f2f6eaecb6b208e82d315aa01`. Does not alter the production Vandal Hearts Remake, original PS1 game assets, Nintendo Switch guest NRO or six source-pinned baseline archives.

## Genuine prerequisite

[Stage286 GitHub Actions #39488411117](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39488411117) **SUCCESS**: 11 ROM-free lifecycle overlay tests and pre-existing Stage274 instrumentation tests passed. Actual `rustfmt`, exact source SHA, Rustarmic submodule and Cargo.lock provenance checks passed. Native `cargo check --locked -p nexium-runner --no-default-features --features backend-rustarmic` type-checked the additive CPAL stream build/play/error/Drop counter code on Linux. The original initial failing compilation was due to one extra Rust formatting placeholder, subsequently fixed and rechecked in the successful run. No executable had been produced by Stage286.

## Stage287 exact executable build

The new `map02-nexium-cpal-lifecycle-host-build.yml` job:

- Fetches public immutable upstream `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219` and the Git-pinned Rustarmic submodule.
- Re-runs both old Stage274 and new Stage286 ROM-free overlay tests and applies the **two consecutive source patches** to that pristine checkout. It records exact intermediary/final `audio.rs` SHA-256 and rejects changes outside the three previously approved host source/manifest paths.
- Rejects any dependency graph change from Cargo.lock SHA-256 `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`.
- Builds a genuine **Release Linux x86-64 NeXium GUI executable** with backend-rustarmic and required CPAL/ALSA/GTK/Vulkan libraries.
- Verifies the actual executable ELF SHA-256, link dependencies and the presence of both the older `VH_MAP02_CPAL_TRACE_PATH` marker and **new** `VH_MAP02_CPAL_LIFECYCLE_PATH` / `map02-cpal-lifecycle` markers.
- Separately archives the research ELF and build/source provenance logs **only if checks succeed**. No ROM, original music, game PCM or user asset is uploaded.

This will be a **different compiled binary** from the baseline NeXium SHA `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`; the baseline is deliberately not overwritten.

## What successful compilation cannot prove

Even a successful Stage287 build does **not** demonstrate that the new executable starts under software Vulkan, runs a generated guest NRO, emits any lifecycle records, resolves the 21-ms callback stop, preserves original game soundtrack, or outputs physical Switch audio. Each requires separate runtime checks, and additional background telemetry itself can change scheduling.

The next gate is a source/SHA-bound **no-ROM startup** check of the new ELF, then a controlled 21/22-ms guest replay with both counter paths, independent optical guest CRC and raw virtual PCM evidence. The error-callback counter records the number of error-handler calls, not exact timestamps, and the reporter's 200-ms snapshots only bracket those events.

**Keep all experimental PRs Draft; no merge without further evidence.**
