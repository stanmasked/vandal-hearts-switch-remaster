# Stage 259 — Switch NRO emulator smoke-test handoff

Status: **EMULATOR NOT RUN** / **HARDWARE NOT TESTED**.

## Verified candidate (real downloaded GitHub artifact)

- Build workflow: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39034607288
- Exact build SHA: `63c718679715adc809a3feb8845a15a37e645488`
- GitHub artifact ID: `12101269376`
- ZIP SHA-256: `becee11263421d3c723dfccc9d8e8b7d077e50d66f850a378baeab0494a50517`
- NRO name: `vandal-hearts-prototype.nro`
- NRO size: `266296` bytes
- NRO SHA-256: `8068eeef36cc1b3751bb4a9d320de5477c85687af018f1323dbba0b33d26b7ad`

Local offline check on 2026-10-17: ZIP members exactly the NRO and `tactical-native.sha256`; zip CRC check passed; extracted NRO matched ZIP payload byte for byte; NRO contained magic `NRO0` and an in-bounds three-segment header (declared binary size 249856 bytes).

## Emulator prerequisites and safety boundary

Use an emulator capable of homebrew `.nro` and a host graphics backend that it supports. Record **emulator name, exact version/build, OS, GPU/backend, loader settings** and whether the user *actually* opened this exact NRO. Do not equate a successful compilation or structural header check with a runtime boot. Firmware and keys must only come from authorized/user-owned sources where required; this homebrew build must never be used as a pretext to distribute copyrighted console firmware, production game images or keys.

The current assistant's Linux container has no recognized Switch emulator executable or exposed `/dev/dri` GPU device; it therefore **did not run the NRO**. Do not fabricate screenshots, logs, timings or audio playback results.

## Smoke-test sequence on an emulator-capable host

1. Verify SHA-256 of the *local downloaded* NRO against the pinned value above, then note the canonical path. If mismatched, **STOP**.
2. Try opening the NRO as a homebrew application. Capture the emulator name/version, launch mode, application log and first video frame (or an exact loader error). **BOOT_PASS** requires independently observed execution, not just parsing `NRO0`.
3. Verify rendered tactical framebuffer is changing as expected and captures contain actual emulator pixels. Distinguish blank/synthetic heartbeat frames from a verified gameplay scene. The project is still a homebrew prototype, not the original full PS1 game.
4. Test controls (including exit), leaving exact input mappings and transitions in operator notes. Mark unsupported host input or home-button semantics as **NOT_TESTABLE**, not success.
5. Test audio. Distinguish `audout` service initialization from **actually audible** non-silent PCM output. Record emulator audio API/logs and whether sound was heard. A UI state or initialized handle is never proof of sound.
6. Attach original, unedited screenshots and emulator stdout/stderr along with the exact NRO SHA-256 and local environment metadata. Save a human-issued verdict separately; do not write **PASS** without the corresponding trace.
7. Home/sleep, true SD persistence, output switching and physical latency remain **HARDWARE NOT TESTED** regardless of emulator outcome.

## Result categories

- `EMULATOR_NOT_RUN`: environment missing, or executable never launched.
- `EMULATOR_BOOT_FAILED`: attempted actual load with captured loader/runtime failure.
- `EMULATOR_BOOT_CONFIRMED`: actual executable start observed, without necessarily confirming graphics/audio.
- `EMULATOR_SMOKE_PARTIAL`: some aspects captured, others unsupported/unverified.
- `EMULATOR_SMOKE_PASSED`: boot, visible framebuffer, tested controls and confirmed audible/recorded non-silent audio supported by operator evidence. This is **not** physical Switch acceptance.

No emulator test results from a future test session should be backdated to this stage.
