# MAP02 Stage293 — genuine CPAL error messages, without confusing logs with event counters

**Research-only Draft / DO NOT MERGE.** Child of independently successful [Stage292 Draft PR #360](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/360), exact frozen head `b00e4e5876f108d309da6edf9067fe54e9d190ad`. No licensed PS1 ROM/audio, NeXium executable, guest research NRO, Vandal Hearts Remake gameplay code or archived experiment is modified.

## Established facts, not new causal inference

[Stage292 Actions #39498313087](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39498313087) successfully independently redecoded the real guest optical PNG, original raw virtual PCM and original CPAL **L-prefixed monotonic counter** CSV for two separate real guest experiments, revalidating their exact ELF/NRO SHA-256. **Requested 21ms** [Actions #39497887866](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39497887866): one guest prejoin audout entered without return, no new postinput CPAL entries or errors, no new AudioOut appends, zero nonzero virtual PCM, final optical guest CRC unverified; CPAL lifecycle state 3 shows only an earlier successful `stream.play()`. **Requested 22ms** [Actions #39495636729](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39495636729): guest CRC **8/8**, 2,244 CPAL callbacks entered and returned, 261 AudioOut appends and 510,838 nonzero PCM16 samples; **36 CPAL error callback count increments** despite working guest audio and the same earlier successful `stream.play()` state.

Both tests used exact lifecycle-instrumented NeXium ELF SHA-256 `c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65` and generated-only opt-in guest NRO SHA-256 `371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`. This is a **single new-ELF A/B pair**, not repeated sampling.

## New offline experiment

Stage293 downloads **only those two exact GitHub Actions archive IDs**, runs the full Stage292 independent pixel/raw-PCM/real-monotonic-CPAL provenance recheck, and then reads the already-captured `nexium-guest-stdout.log` files **without restarting NeXium or the guest**.

The new analyzer inventories explicit `cpal stream error:` messages emitted by the CPAL error callback, lexical descriptors for recognizable text (e.g. ALSA, xrun, backend), the whole-process error message count, distinct normalized exemplars, and original stdout SHA-256 and byte count. It also counts other audio warnings separately. This helps test whether the nonzero CPAL error callback counter observed during a *working 22ms guest* produced useful error text.

**Crucial attribution limit:** the host log lines have no independently verified per-event **monotonic guest-input clock**. The `L` counter's 36 increments are measured inside the real postinput guest window, while host stdout may contain messages from before or after that window. **Do not assume the count of stdout lines must equal 36, or that a log line corresponds to a specific callback**, especially where filtering or suppression may occur. If stdout contains no explicit CPAL error messages despite a nonzero counter, the correct outcome is “captured stdout does not reveal the reason,” not an invented ALSA cause.

The scanner fails closed on missing, symlinked, empty or unexpectedly oversized stdout. It sanitizes embedded paths/addresses/numeric identifiers in any short message examples; it records only a summarized JSON receipt, never reuploads the original raw host logs. The workflow runs **18 ROM-free adversarial synthetic tests** before independent real archive reading.

## Scientific boundaries and future work

The error callback count does not by itself demonstrate audio failure: the actual 22ms guest ran successfully with 36 such callbacks, while the 21ms guest stopped showing postinput callbacks without any new reported errors. CPAL lifecycle state 3 means **a historical successful play request**, not proof the stream remains active. Requested Pulse hint 21/22ms is not a measured ALSA period. Neither one-pair logs nor lexical tokens reveal exact scheduling, stack traces, CPAL/ALSA root cause, permanent `audoutPlayBuffer` deadlock, original PS1 soundtrack fidelity or physical Nintendo Switch audio.

Only if messages reveal a meaningful new distinction should a separate, bounded **source-pinned runtime intervention** be designed. The original six-run old-host baseline and both new-host guest archives stay unchanged. All research PRs remain Draft and none should be merged into production game code.
