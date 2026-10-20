# MAP02 Stage285 — localize callback transitions without inventing a root cause

**Research only — Draft / DO NOT MERGE.** Child of validated [Stage284 PR #321](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/321), exact parent commit `3786510115a4d0be76e7e1fc2bc004178839f23d`. No emulator, guest NRO, game audio or user ROM modified.

[Stage284 Actions #39481359555](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39481359555) independently confirmed the six actual opt-in guest runs: three requested 21ms produced a pending guest audout prejoin call with no subsequent CPAL entry or nonzero virtual PCM; all three 22ms runs completed guest 8-page CRC with CPAL and nonzero PCM. This establishes observed repeatability but not the transition's exact onset or mechanism.

## A narrower forensic question

The existing Stage274 host instrumentation emits cumulative CPAL callback entry/return counts and guest AudioOut counters at approximately **200ms** snapshot intervals. This allows a **bounded interval** for any observed counter change but does not measure each callback's timestamp.

Stage285 re-downloads the six immutable raw guest trial archives from run #39479885398 and uses the already-tested strict reporter parser to validate each full monotonic timestamp series. The new `tools/audit_map02_cpal_callback_transition.py` separately computes each sample interval whose CPAL entry counter rose. It then marks intervals entirely after the first controller-input clock and intervals crossing that boundary, and records last pre-input counts, post-input deltas, and observable callback activity.

This prevents an unsupported assertion such as “the CPAL callback stopped exactly when the guest entered audoutPlayBuffer”: the guest screenshot and CPAL counter timestamp may be hundreds of milliseconds apart. The pipeline also cannot yet distinguish stream pause/error, Linux/PulseAudio scheduler starvation, or callback teardown without **separate, opt-in CPAL stream lifecycle/error callback instrumentation**.

## Acceptance, evidence and boundaries

The Stage285 CI downloads **only six historical artifacts**, performs no new emulator boot and no new ROM upload, runs ROM-free tests and fails closed if any original CSV, input time or stored host parser receipt is inconsistent. It must reproduce **zero fully post-input CPAL entries at 21ms** and positive activity at 22ms before a bounded result is issued. Each finding carries precise flags stating that exact onset and causality remain unproved.

The next isolated intervention should add opt-in, allocation-free **CPAL stream lifecycle events** (build/play/result, CPAL error callback, pause/drop and device/configuration identity) with monotonic host clocks while preserving the six-run baseline and checking that the instrumentation itself does not change the boundary. This is an experimental design proposal, **not a claim that these events have been implemented or measured**.

No claim is made about a permanent guest service deadlock, the original PS1 game's audio, a production game fix or a physical Nintendo Switch speaker/DAC.
