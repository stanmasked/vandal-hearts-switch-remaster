# MAP02 Stage282 — independently re-decode the one matched 21/22-ms CPAL guest pair

**Research-only Draft / DO NOT MERGE.** Child of actual 21-ms [Stage281 Draft PR #308](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/308), frozen at `415b62e717269b07cf1a7fe3215ebccf8a6a62a7`. No Nintendo Switch game code, original licensed ROM/PCM, NeXium executable or earlier guest experiment is modified.

## Genuine independently stored input experiments

- **21-ms requested Pulse hint**: [GitHub Actions #39475359613](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39475359613) produced a bounded guest prejoin panel with `audoutPlayBuffer` entries/returns **1/0**, stage `ENTERED_PLAYBUFFER`. Its final eight-page CRC panel remained unverified; the virtual 48k/stereo PCM contained **0 nonzero samples**. The raw CPAL reporter (about 33.8 seconds of observed snapshots) showed **0 new callback entries or returns after game input**, though exactly 1 callback had entered/returned before the input marker. New kernel `AudioOut` appends/releases after input: **0/0**. CI intentionally classified this as *pending audout return at finite prejoin snapshot*, not a permanent service deadlock or successful strict PCM test.
- **22-ms requested Pulse hint**: [GitHub Actions #39473162070](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39473162070) validated the actual guest optical CRC **8/8 pages** with zero mismatches, **541,820 nonzero virtual PCM16 samples**, CPAL entry/return pairs **2,242/2,242** since input, and kernel `AudioOut` append/release counts **277/278**. Guest prejoin `audoutPlayBuffer` returned **487/487** by the snapshot, stage `CLEANUP_COMPLETED`.

Both runs used the **same compiled Linux NeXium executable**, SHA-256:

`dd4ed55b6ce8477f19b77465f4ce6a0606b7a7315b3a0e2b8137b7d7ab5effd0`

and exactly the same **ROM-free opt-in guest NRO**:

`371c9fd9f1f41ad87cbb5f7f96a3e5e9d56878f8cfff2bf7fea2c17120c2611b`

The Stage281 launch procedure was source-compared against the successful Stage280 run, allowing only the Pulse hint **22→21** and stage-specific output paths. All other controller input sequence, observation periods, compiled CPU backend (Rustarmic), NRO contents and virtual sink configuration were held fixed.

## Stage282 independent source-evidence audit

Previous trial-level reports were produced within each original run; comparing their printed values alone would not independently protect against transcription or tampering mistakes. This stage downloads **the two actual original GitHub Actions evidence archives** and independently:

1. Revalidates exact run IDs, source SHA, attempt, binary/NRO SHA and research-only expected provenance from each archive.
2. Re-decodes the **actual guest prejoin magenta optical PNG** using the independently implemented CRC-8, then recomputes the exact strict eight-page final PNG optical result. The 21-ms failure must still decode as *unverified*, rather than fabricated success.
3. Re-parses the actual ~200-ms monotonic **host Rust CPAL/AudioOut raw CSV** with exact real first-controller-input and last-screenshot marker values; verifies the saved per-run JSON equals the recomputed raw counter series.
4. Independently reads **each actual 48-kHz/stereo raw PCM file** and recomputes its SHA-256, byte length and nonzero PCM16 sample count.
5. Only then considers the pair a matched-host/NRO contrast if its real 21-ms archive has a pending prejoin audout call, zero later callback/appends/PCM, while the real 22-ms archive has a fully completed eight-page guest CRC, positive callback/appends/PCM, and matching guest calls/returns.

`tools/audit_map02_cpal_paired_21_22.py` fails closed on any mismatch. The independent workflow also runs 14 adversarial synthetic comparison tests, including falsifying source identities, callback progress, optical page counts, raw PCM and guest buffer evidence. Its only output is a small JSON comparison receipt; it does **not** reupload the old raw captures.

## Scientific limits

**This is one A/B pair, not repeated confirmation or a causal root-cause proof.** The difference is shown under a **requested Pulse latency hint**, not a measured CPAL callback period. The evidence does not establish an infinite audout deadlock, distinguish every possible host scheduling cause, prove the original PS1 game's soundtrack or demonstrate sound on a physical Nintendo Switch. The new source-pinned NeXium host binary also differs from the older nightly tested in Stage273.

After Stage282 passes, the next major scientific gate is **three independent repetitions of 21 ms and three of 22 ms with one immutable new host executable**, using the same auditable guest/CPAL/PNG/PCM machinery, followed by independent cross-run variance analysis.

**Parent PRs and main untouched.**
