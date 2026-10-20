# MAP02 Stage279 — real instrumented NeXium GUI startup without game data

**Research-only Draft / DO NOT MERGE.** Child of successfully verified [Draft PR #297](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/297) at frozen SHA `ca54ca70aa82d03d7f81a827d85cce21b73353d3`. Adds only an opt-in CI workflow and this document; no NeXium Rust code, Vandal Hearts gameplay/audio code, release, or original ROM changes.

## Locked host prerequisite

Independent [Stage278 Actions #39470415349](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39470415349) **SUCCESS**: the real Stage276 ELF artifact from [source build #39467347590](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39467347590) was downloaded again and independently verified using **17/17** generated-only tampering tests, source/lockfile identities, real Linux ELF properties, SHA-256, exact instrumented source overlay paths, and opt-in CPAL markers.

**Exact compiled host ELF SHA-256:** `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`.

Upstream NeXium source: `089562567a0a8760dfdd8420e1f57c35159a9219`. Stage275 dependency lock: `e6e8fcb90624650afddd1f25327dd4e6b042b094e8336cb5f43d2dc370e28739`.

## Stage279 actual host process launch

This stage fetches the **same compiled binary artifact** from run #39467347590, verifies its SHA again and **actually executes it without a game ROM, guest NRO, firmware or original music**. The GitHub-hosted Ubuntu runner supplies:

- A virtual X11 display (`Xvfb`), software Vulkan via Mesa's lavapipe ICD, isolated HOME and XDG runtime directories, and the NeXium GUI's runtime shared libraries.
- A 48-kHz stereo virtual PulseAudio null sink, intentionally disconnected from physical audio hardware.
- A bounded, independently reaped GUI process. CI searches for a **real visible window named NeXium**, checks the process remains alive after a short period, obtains a real X11 PNG screenshot, and stores the window title, software Vulkan/Pulse configuration and host log.

If the GUI never becomes visible, the process exits, a required shared library is missing, or a screenshot fails, this stage reports **UNVERIFIED** rather than a false successful boot. Logs and any partial screenshot are retained to debug the result.

If successful, the final JSON receipt is bound to the independently verified executable digest and includes actual GUI screenshot/log SHA-256. The artifact contains **no user's private game resources**.

## Limits even for a successful result

An empty GUI with no Switch guest does **not** exercise the game-specific CPAL output closures or kernel `AudioOut` service. The internal reporter is only started in the game's normal CPAL-stream initialization path, which may never run without a guest; missing `VH_MAP02_CPAL_TRACE_PATH` samples in this no-ROM test is **expected** and cannot imply CPAL failure.

A green GUI startup does not prove physical Switch DAC/speaker output, the original game's soundtrack, correct guest buffer release, a 21-ms audio repair, or equivalence to the historical nightly. It is the narrow prerequisite for the next **separate controlled 21/22-ms × 3 guest NRO** experiment using the same compiled host hash, enabled CPAL counter path, optical CRC-8 receipts, raw virtual PCM capture and an independent source/run-ID evidence audit.

**Main and all ancestor research PRs remain untouched.**
