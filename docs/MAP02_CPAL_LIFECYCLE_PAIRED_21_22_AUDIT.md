# MAP02 Stage292 — independent new-lifecycle ELF 21/22-ms guest, CPAL and PCM comparison

**Research-only Draft / DO NOT MERGE.** Child of [Stage291 Draft PR #357](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/357), corrected parent head `af17517c7ee65855427a910559b59fe02355019f`. The initial Stage291 workflow [#39496853360](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39496853360) failed before running NeXium, because its changed-file allowlist inherited the 22ms documentation pathname. That run is **not game-audio evidence**; use the corrected actual Stage291 trial [#39497887866](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39497887866).

## Two exact binaries and an independently pinned guest

The target exact host is the actual Stage287 instrumented NeXium Linux x86-64 ELF:

`c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`.

The original generated-only research guest NRO is SHA-256:

`371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`.

Both requested 21/22-ms test scripts use the same host ELF, guest NRO, Rustarmic, virtual 48-kHz stereo Pulse sink, controller route and screenshot timing, except requested `PULSE_LATENCY_MSEC` and independent evidence paths. The 22ms real Stage290 run [#39495636729](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39495636729) **PASSED** strict guest 8/8 CRC, 510,838 nonzero virtual PCM16 samples, CPAL callback 2244 entered/2244 returned, 261 kernel AudioOut appends and observed **36 CPAL error callback increments despite successful guest audio**. Lifecycle state `3` records the successful earlier `stream.play()` call; it does not guarantee later continuous activity.

Stage292 must **not** conclude anything about 21ms until it downloads the original *successful* corrected Stage291 archive #39497887866 and independently confirms real guest evidence.

## Independent raw-evidence recheck

The new audit downloads each **actual source-run archive** from fixed GitHub Actions IDs, then independently re-decodes the true prejoin optical PNG and final eight-page CRC-8 status. It reparses the original `L`-prefixed monotonic Rust CPAL/AudioOut lifecycle and error-count trace with guest input/final clock markers and cross-checks stored JSON. It rehashes the raw virtual Pulse PCM16 capture and recalculates every nonzero sample count. It rejects mismatched Stage290/291 run ID, hint, attempt or SHA-256, missing guest images, truncated PNG/PCM, source mismatches and invalid lifecycle counters.

Fourteen ROM-free adversarial tests challenge classification. Unlike the previous six-run evaluator, the new source parser reports both a verified one-pair contrast and **fully evidenced mixed/unexpected behavior**, rather than assuming that new instrumentation preserves the old-host 21ms boundary. If the corrected Stage291 archive is unavailable or unverifiable, CI must fail closed and produce `UNVERIFIED`.

## Interpretation

Even an exact pair with a 21ms pending `audoutPlayBuffer`, no callback activity and 22ms successful guest audio would support **one matched pair** on this changed instrumented host, not repeatability. An observed CPAL error callback count is not a timestamped error reason; successful 22ms audio with 36 error callbacks already demonstrates errors alone are not dispositive. A `stream.play` success flag does not guarantee that the stream continues to run. Requested Pulse latency is not measured ALSA/CPAL device callback period.

The auditor cannot establish root cause, infinite deadlock, original PS1 soundtrack accuracy, physical Nintendo Switch speaker sound or a production audio fix. The original Stage284 six-run old-NeXium result remains separately preserved, unaltered.

No original ROM or licensed assets are added to GitHub; only research audit and documentation files. **Do not merge to main.**
