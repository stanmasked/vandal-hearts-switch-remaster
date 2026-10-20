# MAP02 Stage287 — compiled CPAL lifecycle/error-probe NeXium host

**Research-only Draft / DO NOT MERGE.** Based on the successful [Stage286 Draft PR #345](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/345), frozen head `95a89aa0e43f1a28b8d4e25b477f7aa7e4045ee7`. No Nintendo Switch game code, user ROM, soundtrack or released emulator is modified.

## Verified prerequisite

[Stage286 GitHub Actions #39490254762](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39490254762) completed successfully with **5/5 synthetic anti-double-patch and source-anchor tests** and genuine Linux `cargo check --locked` of source-pinned upstream NeXium, Rustarmic CPU backend, CPAL callback, and kernel AudioOut. Toolchain `rustc 1.99.1`; dependency graph `Cargo.lock` SHA-256 `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`. This was a type-check, not executable output.

## New exact-source release build

Stage287 reuses the previously successful Stage276 release-build workflow and immutable upstream `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219`, including its pinned `rustarmic` submodule. The flow:

1. Checks the exact current research PR SHA and a **strict two-file-only child diff** (this workflow and documentation).
2. Applies the original Stage274 generated opt-in **CPAL callback** and guest **AudioOut** counters to the **exact three upstream source paths**. Revalidates the original source-overlay receipt and all existing tests.
3. Applies the already typed and tested Stage286 lifecycle overlay **after** the Stage274 patch, adding CPAL build/play result states, error callback count, and opt-in **L-prefixed** host 200ms samples. Again checks all five Stage286 synthetic source-patch cases and original Rust syntax.
4. Resolves Cargo dependencies and refuses the build if the lockfile SHA differs from the independently proven Stage275/Stage286 value.
5. Performs an actual optimized `cargo build --release --locked -p nexium-gui --bin nexium --no-default-features --features backend-rustarmic` on Ubuntu x86-64. Confirms a Linux ELF, runtime linker dependencies, and embedded opt-in reporter markers.
6. Only upon success publishes a **new and separately hashed** research NeXium ELF, build manifest, compiler logs, source overlay paths, lifecycle-patched `audio.rs` SHA and dependency lock. No original game assets are packaged.

This new host is **not byte-identical** to previously verified Stage276 ELF SHA-256 `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`. Compiler optimization and lifecycle probes may also perturb host scheduling.

## Evidence boundaries and next controlled experiment

A successful release build would prove only creation and source provenance of a new instrumented host executable; it **does not prove** that the host GUI starts, that the lifecycle CSV reporter emits valid values, that any CPAL error event occurs, that the guest boots, or that the 21ms/22ms audio boundary persists under the new probe.

The next separate steps are to inspect the new ELF and SHA, run a bounded real host/guest smoke test with the exact same ROM-free research NRO, validate the new L-prefixed callback/lifecycle samples, and then repeat 21ms/22ms controlled trials on this *new* fixed binary. Original [Stage284 six-trial evidence #39481359555](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39481359555) remains the unchanged baseline.

The error callback *counter* and 200ms atomic state samples do not independently timestamp each callback or prove a CPAL stream pause/drop, ALSA wakeup failure, permanent guest deadlock or physical Nintendo Switch sound.

**Production code and main branch unchanged. Do not merge the experiment.**
