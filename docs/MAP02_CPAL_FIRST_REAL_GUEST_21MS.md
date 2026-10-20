# MAP02 Stage281 — real 21-ms control on the exact same NeXium and generated guest NRO

**Research-only Draft / DO NOT MERGE.** Child of independently verified [Stage280 Draft PR #301](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/301), frozen parent source SHA `3e24e1f1d706aac027ae14afea505a921a050425`. This stage neither changes production Nintendo Switch game code nor uploads any original game ROM, art, soundtrack or PCM.

## Last confirmed real 22-ms positive control

[Stage280 actual guest Actions #39473162070](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39473162070) **PASSED** after selecting Rustarmic explicitly. Guest prejoin optical marker passed, strict final 8/8 PCM CRC-8 pages passed (zero mismatches), raw virtual PulseAudio capture contained 541,820 nonzero PCM16 samples, and the independent real 200-ms CPAL / AudioOut timeline analyzer passed.

From the input-to-final observation window in that run:
- CPAL callback entries / returns: **2,242 / 2,242**.
- CPAL output frames: **1,147,904**.
- Guest kernel AudioOut appended buffers: **277**.
- Guest AudioOut released buffers: **278**; accepted frames **153,905**.

The exact compiled NeXium ELF SHA-256 is `dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`. The guest is the same independently pinned ROM-free research NRO artifact from run #39460035568; neither executable is rebuilt in this stage.

## One-variable 21-ms negative control

This stage copies **the entire successful Rustarmic guest launch script**; CI compares the two scripts byte-for-byte after normalizing only the stage-scoped evidence paths (`stage280`→`stage281`) and the single variable `PULSE_LATENCY_MSEC=22`→`21`. It refuses to run if other changes (controller inputs, time budgets, sink rates, CPU backend, binaries, audio capture, screenshot strategy) are discovered.

The workflow downloads the **exact prior ELF and exact generated-only NRO** from successful historical artifacts, checks source SHA, NRO0 header, hashes and original research run. It then requests 21 ms on the same virtual 48-kHz PulseAudio null sink and collects:

- Actual pre-input, prejoin, final and late guest screenshots; optical prejoin stage with bounded audout entry/return counts.
- Independent Rust CPAL callback enter/return/frame counts and kernel AudioOut accept/release counts, sampled every ~200 ms with monotonic guest input and final-observation markers.
- Real raw monitor PCM, with SHA-256 and nonzero PCM16 sample count.
- Original strict eight-page guest CRC-8 final receipt, which is recorded even when incomplete.

The new classification distinguishes **strict final guest completion with nonzero virtual PCM** from **an audout call still unreturned in the observed prejoin screenshot**. The latter is an observed pending return at a finite snapshot, **not proof of a permanent deadlock**. If neither result can be established, CI fails as `UNVERIFIED_GUEST_21MS_OUTCOME`, preserving all evidence for diagnosis. A stalled guest is not silently marked as having passed the original strict guest CRC; its optical result is retained separately.

## Scientific limits

- A requested `PULSE_LATENCY_MSEC` value is a host Pulse client hint, **not measured CPAL period** or device-reported latency.
- Stage281 is **one** 21-ms trial; it cannot establish repeatability by itself or the root cause of the earlier nightly-host boundary.
- Although the exact new ELF/NRO bytes are reused, changes in virtual CPU scheduling, audio streams and guest input timing may still affect outcomes. The new source-pinned executable differs from the historical nightly.
- Even a confirmed 21-ms audio stall would not demonstrate perpetual AudioOut deadlock, production game audio repair, original PS1 soundtrack correctness or sound on physical Nintendo Switch hardware.

If the paired one-run results are interpretable, the next step is an independent **3×21ms + 3×22ms** replay with a single host ELF SHA-256, actual guest screenshots and virtual PCM, plus a six-run cross-archive auditor.

**No merge to main.**
