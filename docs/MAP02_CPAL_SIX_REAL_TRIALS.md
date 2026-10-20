# MAP02 Stage283 — six real CPAL/AudioOut guests with one immutable NeXium ELF

**Draft / DO NOT MERGE.** Child of independently successful [Stage282 Draft PR #312](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/312), frozen at `3c7735148e360607c99717730677172241d87634`. No production Nintendo Switch game changes, original game ROM, copyrighted audio, or newly compiled NeXium builds.

## Empirical prerequisites

[Stage282 independent actual-archive audit #39477450472](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39477450472) **PASSED** all 14 synthetic challenge tests, redecoded the original raw guest PNG optical markers, independently parsed host Rust CPAL/AudioOut monotonic counters, and checked SHA-256 and nonzero PCM16 directly from raw 48kHz virtual captures. The one verified matched 21/22ms pair showed:

| Observable after input | Requested 21ms | Requested 22ms |
|---|---:|---:|
| Prejoin guest `audoutPlayBuffer` entered/returned | 1 / 0 | 487 / 487 |
| Host CPAL callback entered/returned | 0 / 0 | 2242 / 2242 |
| Kernel AudioOut accepted appends | 0 | 277 |
| Nonzero virtual PCM16 samples | 0 | 541,820 |
| Guest eight-page CRC optical receipt | Unverified | 8/8 valid |

This is **one matched pair**, not yet evidence of repeatability. The 21ms `audoutPlayBuffer` is unreturned **at a finite prejoin snapshot**; this does not prove it can never return.

## Exact immutable source inputs reused for ALL SIX guests

- Newly compiled Linux x86-64 NeXium with opt-in real CPAL/AudioOut atomic counters, ELF SHA-256 `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`. Binary created in [Actions #39467347590](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39467347590); source NeXium Git SHA `089562567a0a8760dfdd8420e1f57c35159a9219`.
- Exactly the same **ROM-free opt-in generated research NRO**, SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`, originally built in [Actions #39460035568](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39460035568).
- Exactly the Stage280/281 successful, source-compared Rustarmic guest launch scripts. They differ **only** in `PULSE_LATENCY_MSEC=21` vs `22` and stage-scoped temporary file names; not the input sequence, screenshot checkpoints, timeout, CPU backend or virtual 48k stereo Pulse sink.
- No original game disc image, music file or private data are uploaded to GitHub.

## Six independently hosted jobs and cross-run evidence

`.github/workflows/map02-cpal-six-real-trials.yml` runs a **six-job matrix**, `(21ms,1..3)` and `(22ms,1..3)`, with fail-fast disabled. Each runner downloads and independently hashes the exact same host ELF and NRO before starting. Each receives its own isolated virtual X11/software Vulkan/48k Pulse environment, fresh guest process, actual controller input timestamps and opt-in CPAL reporter.

Every job retains its own evidence archive, including real preinput, prejoin, final and late PNGs, raw 48k stereo PCM, original host CPAL/AudioOut timestamped CSV, per-image optical receipts, raw PCM hash and nonzero count, host/NRO source attestations and explicit matrix hint/repeat/run identity. Guest audio not completing is **not** silently relabelled as a successful CRC test.

After the guest matrix, a separate aggregator downloads **all six** job archives and rejects a missing/duplicate repeat. `tools/audit_map02_cpal_six_real_trials.py` re-decodes actual optical PNGs (with their CRC-8/CRC32 checks), reparses raw host CPAL time series against measured monotonic guest input/final times, and independently recalculates raw PCM16 sample counts/SHA-256. It enforces one binary SHA and one NRO SHA across all runs, original guest source, exact current workflow run/attempt, and archive-to-matrix hint identity.

The independent auditor records each outcome **as observed**: a fully completed guest with real PCM, a finite pending guest audio return with no post-input CPAL/PCM, or another honestly captured outcome. An unexpected success at 21ms or failure at 22ms produces a **mixed/changed-behavior result** rather than hiding that trial or manufacturing a repeated boundary. Missing source evidence produces `UNVERIFIED` and fails the audit. Sixteen generated-only tests challenge the aggregator's acceptance rules.

## What six passes would and would not prove

Six complete and consistent archives would strengthen repeatability of the **requested Pulse latency hint** behavior under six distinct CI guest processes on one source-pinned Linux host. This hint is not a measured hardware callback period; six matches would **not** establish the root cause of CPAL scheduling, infinite `audoutPlayBuffer` deadlock, physical Nintendo Switch DAC output, actual original PS1 soundtrack preservation or a production game audio fix.

The newly built Rustarmic NeXium differs from older nightlies. Any subsequent fix should be a separate controlled intervention with new exact source hashes and repeated 21/22ms measurements. This Stage283 branch remains **Draft**, with all parent PRs and the actual Vandal Hearts game code unchanged.
