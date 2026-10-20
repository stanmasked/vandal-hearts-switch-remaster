# MAP02 Stage269 — independent raw PulseAudio sink-input ordering

**DRAFT / DO NOT MERGE**. Frozen research-only child of [Draft PR #263](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/263) at exact head `b6f93340a95506e783303311881ea1c6f58ec24a`. No game source, NRO build flags, NeXium executable, host parameters, original ROM or original audio are changed.

## Verified prerequisite

The Stage265 GitHub Actions [run #39411672432](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39411672432) successfully compiled and built one research NRO, acquired one NeXium executable and verified a **single executable SHA-256** `5026f934ed7cd7d81a5901e536f5fe29b00e117861d432f9be351730afc7d964` across all six original guest runs. The independent audit (not the six guest jobs) succeeded even though the original 21-ms strict guest jobs correctly failed.

The archival run observed:

| Requested host Pulse latency hint | Repeat | Stage | audout enters / returns | measured PulseAudio 48-kHz sink-input buffer latency (µs) | nonzero virtual PCM16 samples |
|---|---:|---|---:|---:|---:|
| 21 ms | 1 | ENTERED_PLAYBUFFER | 1 / 0 | 10,666 | 0 |
| 21 ms | 2 | ENTERED_PLAYBUFFER | 1 / 0 | 10,666 | 0 |
| 21 ms | 3 | ENTERED_PLAYBUFFER | 1 / 0 | 10,666 | 0 |
| 22 ms | 1 | CLEANUP_COMPLETED | 485 / 485 | 10,333 | 539,707 |
| 22 ms | 2 | CLEANUP_COMPLETED | 481 / 481 | 11,728 | 535,440 |
| 22 ms | 3 | CLEANUP_COMPLETED | 487 / 487 | 10,333 | 541,620 |

**Careful interpretation:** the successful sample at 10,333 µs is **lower** than the unsuccessful sample at 10,666 µs, while another successful sample is **higher**, at 11,728 µs. Thus no strict single increasing or decreasing cutoff on *those six sampled buffer-latency values* separates the two sets. This does **not** falsify all threshold mechanisms, especially not a threshold in a different unobserved quantity such as ALSA period size, CPAL callback rate or guest-service queue state.

## Independent rerun of archival data, not a new emulator workload

The Stage269 job independently downloads the original same-run **nine** archives and verifies:
1. Same verified host executable and archive SHA, exact source SHA and all six per-guest manifests.
2. The same run attempt for NeXium, NRO and all six trial evidence sets.
3. The original NRO digest, all six real PNG guest CRC8/XOR prejoin stages, raw 48-kHz PCM hashes and nonzero sample counts, plus the guest conjunction classification.
4. The original **text** snapshots `pulse-sink-inputs-during.txt` and `pulse-sink-inputs-after-input.txt`, independently reparsed with the existing `report_pulse_sink_input_latency.py` parser and required to reproduce the saved `pulse-sink-input-observed.json` **exactly**, including NeXium-specific ALSA plug-in client, stereo 48-kHz spec, sink-input uniqueness and measured buffer times.
5. A separate actual-outcome-vs-measured-value analysis. Rejects any missing or duplicated trial, fabricated successful PCM/guest stage, parser-output forgery or claim of a literal monotonic cutoff not actually supported by the data.

Ten generated-only negative/positive tests cover missing trials, forged results, false return counts, hint-versus-observation confusion, bogus Pulse metadata and counterexamples that actually *are* monotonic.

No additional NeXium/ALSA/CPAL sampling is introduced into the guest execution path, so these new checks cannot perturb the guest audio timing of the original six trials.

## Open investigation

The 21-ms snapshots establish that the guest entered one real `audoutPlayBuffer` call with no return observed at the fixed prejoin screenshot; the 22-ms snapshots establish repeated call returns and a nonzero virtual Pulse PCM capture. This distinction is reproducible with one NeXium binary, not yet a service-level root cause or permanent deadlock proof.

A next **separate** instrumented experiment must measure actual CPAL callbacks and ALSA buffer/period configuration *with host-side timestamps* and correlate them with guest call entry/return. Instrumentation overhead and host backend changes must be recorded as new test conditions. Physical Nintendo Switch audio remains untested.

**Do not merge research-only evidence changes into main.**
