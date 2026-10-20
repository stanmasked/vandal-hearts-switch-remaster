# MAP02 Stage278 — independent audit of the compiled CPAL NeXium host

**Research-only Draft / DO NOT MERGE.** Branch child of [Draft PR #293](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/293) at exact frozen parent SHA `6eecc49bcc243435ec971e03ab1dedcbe612daad`. Only offline ELF audit source, ROM-free synthetic tests, a one-shot GitHub Actions artifact check and this document are new. No game source, guest NRO, private game disc images, PCM, or NeXium source overlay change.

## New verified prerequisite

The actual [Stage276 Linux Release build #39467347590](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39467347590) **completed SUCCESS**. It built the opt-in CPAL/AudioOut instrumented `nexium-gui --bin nexium` from `nexium-emu/nexium@089562567a0a8760dfdd8420e1f57c35159a9219`, including the upstream Git-pinned `rustarmic` submodule. Its manifest reports:

| Property | Value |
|---|---|
| ELF SHA-256 | `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0` |
| ELF size | 292,008,736 bytes |
| Platform | Linux x86-64 |
| Profile | Rust Release, backend-rustarmic |
| Upstream source Git SHA | `089562567a0a8760dfdd8420e1f57c35159a9219` |
| Frozen Stage276 research source SHA | `6d24825f45f286dc3ec109d25c0abbc9f864e59d` |
| Stage275 Cargo.lock SHA-256 | `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739` |

The successful run uploaded two distinct artifacts: `map02-stage276-experimental-nexium-linux-x86_64` (the executable and build manifest) and `map02-stage276-compiled-host-build-evidence` (source/lock receipts and build logs). **This is a genuinely compiled executable, but no game guest boot or audio runtime behavior was tested in Stage276.**

## Stage278 cross-artifact verification

The new fail-closed auditor `tools/verify_map02_instrumented_nexium_host_artifact.py` and GitHub Actions job independently download the **exact real executable artifact from successful run #39467347590** and verify its bytes again. The checks require:

- Actual x86-64 Linux ELF header, executable type, sensible byte size, and the embedded opt-in CPAL report controls `VH_MAP02_CPAL_TRACE_PATH` and `map02-cpal-counts`.
- The exact ELF SHA-256 above, checked both with system `sha256sum` and the independent Python verifier.
- Manifest source and locked dependency digests, Release/Rustarmic configuration, exact three-file overlay SHA-256 pairs without duplicate or missing paths, and unambiguous source/report schema.
- Explicitly false declarations for historical nightly equivalence, guest boot, CPAL runtime progress, permanent AudioOut root cause, physical Switch speaker sound and inclusion of game assets. These are provenance **declarations and safety limits**, not independent content-forensic scans of the binary.
- No symlink acceptance, changed content, missing execute bit after restoring mode lost by GitHub artifact extraction, omitted source files or unsupported ELF architecture.

Seventeen generated-only Python tests attack these constraints without executing NeXium or loading user assets. Only a small audit JSON receipt is re-uploaded from Stage278; the original 292 MB ELF remains exclusively in the immutable Stage276 research artifact, not committed to Git.

## Interpretation and next gate

Successfully validating this artifact **still does not prove** that the newly compiled NeXium starts on the CI runner, displays the guest, calls CPAL, releases AudioOut buffers, produces meaningful 48-kHz PCM, or solves the 21-ms stall.

Before a six-run A/B, an isolated host smoke test should start **this exact SHA-pinned executable** with no game ROM, a virtual PulseAudio sink and an opt-in absolute `VH_MAP02_CPAL_TRACE_PATH`, checking that NeXium remains alive and the reporter emits valid time-stamped counters. That smoke test itself changes the host runtime workload and should not be equated with the prior nightly. Only after startup/telemetry validation should the exact new binary be tested against the separately built research guest NRO in six 21/22-ms trials, independently preserving guest PNG CRC-8 and raw virtual PCM.

**No merge to main, no original copyrighted game data in public CI.**
