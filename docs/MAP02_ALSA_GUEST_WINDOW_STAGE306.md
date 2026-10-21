# MAP02 Stage306 — original Stage305 ALSA calls during the actual guest-input window

Research-only child of [Stage305 Draft PR #398](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/398). **DO NOT MERGE.**

Source pair: [GitHub Actions #39558740492](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39558740492), stage305 head `193cd92e75bebe31353d345ddc5b961ffa5f30d1`. This source produced two new independently validated 21/22ms *actual* GUI/ROM-free NRO guests on the same immutable NeXium Stage298 compiled ELF; the original Stage305 source-pinned verification returned `REAL_STAGE305_PINNED_GUEST_USERSPACE_ALSA_COUNTERS_SOURCE_REPARSED` for both. No licensed ROM, PS1 soundtrack, Switch hardware output, production code or upstream source was involved.

## What the retrospective measures

The Stage305 original summary measured **entire-process** cumulative library function counts. Stage306 examines two actual Stage305 artifact packages, independently re-parses the retained raw CPAL P/L and ALSA CSV files, verifies the Pulse event CSV SHA-256, and checks the original Stage305 prior source-verified receipts for private Pulse snapshots, virtual PCM and FileLogger data that were intentionally **not** uploaded, then finds the **latest complete Python ALSA snapshot before the exact guest first-input and final-observation monotonic markers**. Only the **difference of these two counters**, broken down by **each independent-trial anonymous TLS alias and exported function name**, is considered *observed within the guest input window*.

Real source samples are approx. 200ms apart. Bracketing samples must be within 1 second of their corresponding source guest markers. Counter differences therefore refer to a **bounded and slightly shortened** measurement window, not a complete exact per-call event stream. We cannot infer an individual ALSA call timestamp from a 200ms counter, nor identify native Linux threads from interposer anonymous TLS aliases.

## Original trial findings (independent source calculation, pending CI confirmation)

| Observed guest-window counter delta | 21ms | 22ms |
|---|---:|---:|
| CPAL callback entries (existing Stage299 source) | 0 | 2244 |
| Audited generated guest optical 8-page CRC | not verified | PASS |
| `snd_pcm_avail_delay` calls | 287147 | 289719 |
| `snd_pcm_avail_delay` EIO | 0 | 24 |
| `snd_pcm_avail_delay` EPIPE | 0 | 1 |
| `snd_pcm_writei` successful calls | 287147 | 289694 |

For 21ms only one observed anonymous alias contributed ALSA calls during the bounded guest input window; those export-level function calls continued despite zero CPAL guest-window callbacks. For 22ms one anonymous alias contributed **2270 `snd_pcm_avail_delay` calls** (24 EIO, 1 EPIPE) and **2245 successful writei calls** while another anonymous alias recorded **287449 entirely successful avail_delay/writei calls**. These are **different threads only within the given process**, not identities transferable to another CI run.

An alias with similar counts to CPAL callback deltas is only a **correlation, not proof of callback-thread ownership**. The 21ms vs 22ms requested Pulse `PULSE_LATENCY_MSEC` hint does not establish any statistically reliable hardware boundary, nor a causal ALSA recovery mechanism. `LD_PRELOAD` itself changes scheduling and symbol lookup; it can miss internal library calls. Do not conflate entire-process ALSA error totals with those in the actual guest-input interval, do not overinterpret zero observed EIO as no backend failure, and do not claim that successful ALSA `writei` means the guest correctly submitted PCM buffers.

A full re-run of the original Stage305 guest/PCM/Pulse/FileLogger auditor is **not possible** from the privacy-filtered ZIPs: raw Pulse sink snapshots, virtual PCM and the GUI FileLogger were not uploaded. Stage306 never constructs fake equivalents. It retains the previously successful original source-verified receipts and independently re-parses the raw data that were preserved. Any absolute claim that all Stage305 raw evidence was re-verified here would be incorrect.

Stage306 is pure read-only audit of original artifacts, with tests and its own source-only workflow; **no rerun/changes to the experimental NeXium ELF, NRO, CPAL code, game, main branch or prior Draft PR**.
