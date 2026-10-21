# MAP02 Stage307 — source-aligned CPAL / exported ALSA temporal coactivity

**Research only / Draft / DO NOT MERGE.** Stacked child of source-verified [Stage306 Draft PR #400](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/400), whose [GitHub Actions #39561307115](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39561307115) passed independent replay of retained raw CPAL P/L and ALSA CSV, SHA of Pulse event CSV, and cross-checks of previously verified Stage305 private raw source receipts.

The actual source pair is the same [Stage305 successful NeXium + generated ROM-free NRO 21/22ms run](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39558740492) on source-pinned NeXium experimental Linux ELF SHA-256 `fb154cbd581826a4f217485eff338badf0ea14c28a82bff258e7baf32c84153a` and unchanged generated research NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`. Only anonymized userspace ALSA `LD_PRELOAD` counters and opt-in host CPAL snapshots were collected; **no original game ROM or soundtrack**, Nintendo Switch hardware, production/game source changes, or NeXium upstream modifications.

## Method — timestamps and what can be shown

Stage307 re-opens the **same two original source Action artifacts** and independently validates the entire available raw P/L, userspace ALSA, retained Pulse event source and prior Stage306 JSON receipt. For each Stage298 CPAL P report time within the real guest first-input/final-observation interval (including the last pre-input P baseline), it selects the **most recent completed** Stage305 userspace ALSA P snapshot at-or-before that CPAL timestamp, and rejects any alignment lag more than 250ms. The two original observers nominally take samples ~200ms apart.

For consecutive aligned sampling intervals, compare original CPAL callback counter delta with each anonymized ALSA thread's exported `snd_pcm_writei` return count delta. Count bins where both increment; bins where only CPAL or only ALSA increments; total and per-bin absolute differences. `snd_pcm_avail_delay` EIO/EPIPE deltas are additionally reported to distinguish error-prone vs silent background streams. **The two observers' timestamps are NOT the same exact atomic event** and matching their samples cannot establish individual ALSA-call or CPAL-callback timestamps.

## Observations from the retained original CSVs (Stage307 independent Actions verification required)

| Source-aligned metric | 21ms | 22ms |
|---|---:|---:|
| CPAL post-input entry increase | **0** | **2244** |
| Real compared 200ms bins | 120 | 119 |
| High-rate background ALSA alias writei count | 289548 | 287383 |
| High-rate alias bins active without CPAL progress | 120 | 0 |
| Lower-rate ALSA alias writei count during guest | **0** | **2244** |
| Lower-rate alias with CPAL progress in same bin | 0 | **119 of 119** |
| Total absolute per-bin difference: low-rate alias writei vs CPAL | 0 at CPAL=0 | **48 across 119 bins** |

At 22ms the sum of exported ALSA `snd_pcm_writei` returns from one low-rate anonymous alias **equals** the host CPAL P callback count over the same bounded reporter-to-reporter measurement window, and both counters increment in every aligned 200ms bin. A separate high-rate ALSA alias is also active, but with >100 times higher call frequency. At 21ms the high-rate ALSA alias remains active in all sampled bins while the host CPAL counter is unchanged; no lower-rate alias shows advancing writei counts in this window.

**Do not mistake these as proven identity or causality:** An anonymous Stage305 TLS alias is **not** a Linux TID, is not the CPAL thread identifier, and its numeric value cannot be compared across separate process runs. 119/119 coactivity bins plus equal totals make an ALSA alias a *candidate* for source-level callback attribution, **not an actual attribution**. `writei` success does not show actual generated guest PCM delivery. Linux ALSA/PulseAudio may service unrelated audio streams in the same host. `LD_PRELOAD` and the extra observer perturb scheduling. The latency numbers are requested Pulse latency hints, not hardware period measurements or a causal 1ms hardware boundary.

The original Stage305 privacy-sensitive raw Pulse input snapshots, original raw virtual PCM and NeXium FileLogger were never uploaded. Stage307 therefore cannot re-run their unavailable raw data, and instead verifies retained source reports against previously successful source-verified audit receipts. The Stage307 artifact contains **only anonymous aggregate counter data**, no raw source CSV or private host details.

No permanent CPAL/ALSA deadlock, ALSA backend root cause, production audio repair, actual Nintendo Switch DAC/speaker playback or licensed PS1 soundtrack fidelity is established by this experiment. Scope: four isolated source-only research files.
