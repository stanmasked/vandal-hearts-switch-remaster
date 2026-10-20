# MAP02 Stage276 — build a real instrumented NeXium Linux host executable

**Research-only Draft / DO NOT MERGE.** Child of [Draft PR #287](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/287) at frozen SHA `7833351fbb646dff1918fc1c7e3f9e04e730454f`. No original game images, ROMs, soundtrack, game audio source or parent branches are altered.

## Actual prerequisite: compilation reached and passed

[Stage275 GitHub Actions #39466205584](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39466205584) **succeeded** after enabling the upstream-pinned `rustarmic` Git submodule and required CPU backend. The real Linux `cargo check` verified Rust types in **both** patched CPAL callbacks and dependent AudioOut handlers. It used `rustc 1.99.1` and generated a dependency graph recorded as SHA-256:

`e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`

This is a genuine type-check but not a compiled executable. The earlier backend-less compilation failure was caused by NeXium's CPU enums, not new audio code.

## New Stage276 proof

The new standalone `map02-nexium-cpal-host-build.yml` workflow:

1. Downloads only the current research source and **immutable upstream** `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219`, including its Git-pinned `rustarmic` submodule.
2. Re-runs all eight ROM-free overlay tests, applies the exact Stage274 callback/AudioOut atomic probes to **three upstream files only**, verifies their original and resulting SHA-256, and checks Rust syntax.
3. Resolves Cargo dependencies and **refuses** to build if the new `Cargo.lock` does not match the exact SHA-256 proven in Stage275.
4. Installs genuine Linux host libraries, then performs an optimized **release executable build** with `cargo build --release --locked -p nexium-gui --bin nexium --no-default-features --features backend-rustarmic`, preserving the full compiler log.
5. If successful, checks the actual Linux x86-64 ELF, shared-library dependencies and embedded opt-in instrumentation markers `VH_MAP02_CPAL_TRACE_PATH` and `map02-cpal-counts`. Generates an explicit binary SHA-256, source SHA, Rust/compiler version and Cargo-lock provenance manifest.
6. Uploads the built binary **only as an isolated research artifact**, not a game release. It contains no user's ROM, PS1 content, audio capture or original soundtrack. Build logs, manifest and source receipt remain available separately, even after a failed build.

## Important differences from Stage273

The previous successful same-run audio research used a downloaded NeXium binary that was verified as identical across six guests, but its **source commit was not authenticated**. The new executable, if built, will have known upstream source provenance **but is not byte-identical to the nightly**. It also contains a new callback reporter which can perturb CPU scheduling.

A successful build does not prove that the Linux GUI starts, the Nintendo Switch NRO boots, CPAL calls back, AudioOut releases buffers, any 21-ms stall is repaired, or sound plays through a physical Nintendo Switch.

Those require a **separate controlled runtime experiment**, preferably 21/22 ms × three repetitions, with one exact new executable SHA and original guest CRC8/PCM and host monotonic evidence. Do not compare its outcomes with the uninstrumented Stage273 results as though no experimental variable changed.

**No merge, no production code change.**
