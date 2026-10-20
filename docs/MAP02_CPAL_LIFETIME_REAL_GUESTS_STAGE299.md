# MAP02 Stage299 — real newly compiled CPAL event timestamps in the guest

**Research-only Draft; DO NOT MERGE.** Child of [Stage298 PR #377](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/377). No licensed PS1 ROM or soundtrack, production Switch code, upstream NeXium commit or game logic changes.

## What was actually built

[Stage298 Actions #39509934054](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39509934054) succeeded, with genuinely compiled new Linux x86-64 NeXium release ELF SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a`, source commit `e801588983a866c76dcedb52e818859a68ad113d`, pinned upstream `089562567a0a8760dfdd8420e1f57c35159a9219`, original pinned Cargo.lock SHA and rustarmic backend. Its Stage298 runner source SHA-256 is `dca4066830d132317ec4ae57f90b1943b785ea871f078844d1ff7da7fcb5040d`.

This is **not** the old Stage287 binary. All guest tests must verify the exact new ELF and immutable original **ROM-free generated research NRO** SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b` (artifact from Actions `39460035568`), with the same original launcher, inputs, virtual PulseAudio monitor and GUI FileLogger as Stage294–296.

## New Stage299 runs

Run two independent Ubuntu 24.04 jobs with requested `PULSE_LATENCY_MSEC` 21ms and 22ms. Export only one new opt-in environment variable to the unchanged guest launcher:

`VH_MAP02_CPAL_LIFETIME_PATH=${MAP02_EVIDENCE}/host-cpal-lifetime-p.csv`

The separate Stage298 `P` reporter gives exact CLOCK_MONOTONIC timestamps for application-side CPAL build/play start, success/failure and RAII retained-stream `Drop`. The unchanged 11-column `L` reporter samples cumulative callback entries/returns and AudioOut events every ~200ms. For every `P` sample, the new auditor **requires exactly matching sample clock and cumulative callback counter in one original `L` sample**, then checks monotonic, ordered event timestamps and the actual guest input-window bounds.

Actual prejoin/final PNG data, guest CRC 8/8 **when available**, captured 48k PCM SHA and nonzero samples, real NeXium GUI FileLogger sanitized message groups, compiled ELF/NRO source receipts and raw P/L traces are revalidated on the runner. Original unsanitized GUI FileLogger files are **not** uploaded.

## What the new evidence can and cannot establish

If 21ms again has no callback increments after the first sampled report even while `play_ok_ns` is nonzero, that is concrete evidence that the application returned successfully from `stream.play()` while subsequent callbacks were not observed. A zero `drop_ns` establishes **only** that the instrumented application-owned RAII wrapper was not observed being destroyed by the reporter. It **does not prove** the CPAL backend never paused/reconfigured, the ALSA thread survived, that a permanent deadlock occurred, or that the emulator/audio was repaired.

The counter in `P` rows is a **sample**, not a timestamp for the first real callback. A previously positive first snapshot cannot be assigned a fabricated exact onset. Stage298 adds instrumentation and can change timing relative to Stage287, so future controlled multi-replicate trials would be required to distinguish scheduling perturbation from existing 21/22ms variability. The Pulse hint is not a measured hardware buffer period. Physical Nintendo Switch speaker audio and fidelity to the original PS1 soundtrack remain untested.

Five research-only additions: one separate workflow, independent P/L validator, independently source-pinned raw proof auditor, generated-only falsification tests, and this document.
