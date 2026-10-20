# MAP02 Stage280 — first real 22-ms research NRO on source-pinned CPAL NeXium

**Draft / DO NOT MERGE.** Isolated child of verified [Stage279 PR #298](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/298) at frozen SHA `08bf2bb47ab63c0f2d21e00a4dea12808de12d3b`. Adds only the new opt-in guest route, separate CI and this documentation; no Nintendo Switch game source or original ROM/audio data are altered.

## Two independently verified prerequisites

- [Stage276 build #39467347590](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39467347590), [Stage278 audit #39470415349](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39470415349) and [Stage279 no-ROM GUI boot #39470970449](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39470970449) confirm the actual opt-in Linux x86-64 instrumented NeXium **exists**, matches the expected digest, and displays an actual GUI with software Vulkan. Compiled host SHA-256: `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`.
- [Original Stage273 six-trial #39460035568](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39460035568) produced a separately opt-in, **generated-only** research Nintendo Switch NRO archive `map02-audout-presubmit-research-nro`. That artifact is pinned to old source Git SHA `04b20024a50327091cff430eb5c28e4722d4ec76`; it is **not** silently relabelled as built from the new Stage280 revision. Its embedded NRO0 header, SHA-256, old run identity and archive receipt are reverified before use.

## Narrow experiment — one 22-ms positive control first

The Stage280 workflow runs the **actual new compiled NeXium** with the old research-only NRO, a virtual 48-kHz/stereo PulseAudio null sink, software Vulkan and a bounded X11 desktop. It requests `PULSE_LATENCY_MSEC=22` **only for the NeXium host**. The environment variable is a *hint*, not an observed host hardware or CPAL callback period.

A controlled virtual key sequence drives the existing opt-in guest screen. The workflow preserves:

- The actual guest pre-input, pre-join, final and late optical PNGs; strict eight-page guest descriptor/PCM CRC-8 proof is evaluated independently.
- A real `parec` capture from the 48-kHz virtual sink, with raw bytes, sample count and SHA-256; no inference of physical Switch DAC output.
- New NeXium **real Rust CPAL callback and kernel AudioOut counter timeline** from the opt-in absolute `VH_MAP02_CPAL_TRACE_PATH`. Its 200-ms monotonic-time snapshots are parsed by the previously validated Stage277 analyzer, with actual host clock input and last-screenshot markers. The analyzer differentiates callbacks entering/returning, frames accepted/consumed and guest buffers released, and rejects missing sample coverage.
- The actual NeXium console log, virtual sink status and ELF/NRO provenance receipts, which are retained **even on guest failure**.

Strict optical, callback and PCM checks are separate; neither a nonzero virtual capture nor a completed callback is allowed to override a failed guest CRC-8 receipt. A missing CPAL timeline is **UNVERIFIED**, not a fabricated zero-callback result.

## Why not six runs immediately?

This is a **new host build with source provenance**, different from the nightly emulator used in Stage273. Even though the same generated guest NRO bytes are reused, the host CPU/backend, optimized build and internal counter reporter have changed. A single 22-ms positive control establishes whether the instrumented host boots a real research guest and produces usable CPAL/AudioOut measurements at all.

Only after its actual guest and trace archives are inspected should a separate repeated **21/22-ms × 3** experiment be designed around one fixed host SHA and an independent six-run artifact auditor.

The software is not a confirmed 21-ms fix, original game soundtrack port, permanent AudioOut deadlock diagnostic, nor a physical Nintendo Switch speaker test. There are **no user ROMs or copyrighted game music in GitHub**.

**No automatic merge.**
