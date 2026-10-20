# MAP02 Stage291 — requested 21ms real guest test on the exact new lifecycle NeXium

**Research-only Draft / DO NOT MERGE.** Parent [Stage290 Draft PR #355](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/355), frozen source head `4a789d841f276cf0cc8656ad32b04de61272e8ad`. The Stage290 22ms test was **queued** when this independent control was authored; do not assume any new lifecycle runtime result until real Actions and evidence are inspected.

## Controlled binary/NRO and one-variable difference

Both Stage290 (22ms) and Stage291 (21ms) download and byte-verify the **same newly compiled Stage287 Linux NeXium ELF**:
`c3803abd7a06fd4081d7d49367cfbd2cedc4bb1650996f1e09fca5788c881b65`.

Both load the identical, independently hashed ROM-free generated research guest NRO from run #39460035568, with `NEXIUM_CPU_BACKEND=rustarmic`, virtual 48-kHz stereo PulseAudio sink, software Vulkan/X11, same controller inputs and screenshot/timestamp intervals. CI compares the two launch scripts **byte-for-byte after normalizing only stage-scoped evidence names (`stage290`→`stage291`) and requested `PULSE_LATENCY_MSEC=22`→`21`**; all other differences are fatal.

Each run retains original host CPAL lifecycle/error `L` snapshots (not merely the old `T` callback counts), raw virtual PCM16, actual guest prejoin/final PNG optical receipts, monotonic guest markers and immutable executable/NRO identity receipts. Strict final guest eight-page CRC is recorded honestly: **failure is not reclassified as success**. The Stage288 independently tested lifecycle parser detects build/play failures, prior `stream.play` success, increase in CPAL error callback counts, and observed callback changes within a bounded guest window.

An additional Stage291 source-evidence receipt distinguishes:
- A guest **really completing all eight CRC pages** with nonzero virtual PCM at requested 21ms;
- A guest `audoutPlayBuffer` call observed **still pending in the finite prejoin screenshot** while final optical CRC remains unverified;
- An **UNVERIFIED** result that fails closed when neither outcome is independently supported.

One 21ms result alone is not proof of repeatability. A prior successful `stream.play()` call does not guarantee that the stream is currently active. An observed pending guest `audoutPlayBuffer` call is **not proof of a permanent deadlock**. Error-count changes are not per-callback timestamps. Requested Pulse latency is not measured host device latency.

## Scientific next step

Only after the new Stage290 22ms and Stage291 21ms exact-binary trial archives are both complete and independently redecoded may we compare them. The original Stage283/284 six-run old-ELF contrast must remain a separate, frozen baseline. If the new instrumentation changes scheduling, an observed difference cannot simply be attributed to the guest code. No original PS1 soundtrack, user ROM, physical Switch DAC or production game code is used or changed.

**Keep all PRs Draft and do not merge.**
