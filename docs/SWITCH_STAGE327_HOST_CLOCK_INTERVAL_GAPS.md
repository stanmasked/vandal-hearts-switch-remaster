# Vandal Hearts Remake — Stage327: independent host clock interval gaps

## Purpose and distinction from game audio

Earlier [Stage304 archived evidence](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39164847668) showed a **−347 ms backward host wall-clock interval** with increasing buffered PCM file size. Stage325 added a second, monotonic host clock to later captures without changing the legacy Stage304 verifier. [Stage326 independent replay](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39168578569) verified two distinct, successful real NeXium capture archives and their original clock-source hashes.

Stage327 adds a **read-only discrepancy classifier** for those verified Stage326 host intervals. A strictly positive wall-clock interval may still disagree sharply with a separate monotonic clock; this classifier makes such cases visible. It does **not** change Stage304/305 acceptance, synthesize PCM, change SPU or `audoutPlayBuffer`, measure guest time, or infer audible sound.

## Confirmed original host measurements

Stage327 computes `wall_delta_ms × 1,000,000 − monotonic_delta_ns` using the **source-confirmed Stage326 intervals**. No absolute host timestamps enter its public receipt.

| Original NeXium host-control interval | Capture 39166023593 | Capture 39167324026 |
| --- | ---: | ---: |
| `before_plus_down` → `after_plus_up` | −687,151 ns | +303,818 ns |
| `after_plus_up` → `control_sequence_end` | +209,810 ns | +220,257 ns |

The second-minus-first **clock discrepancy** changed by +990,969 ns for the first interval, and +10,447 ns for the second interval. Each per-capture absolute discrepancy was less than 1,000,000 ns.

**The one-millisecond marker is only an illustrative diagnostic heuristic.** Its value is not a guaranteed sampling or scheduling uncertainty bound; the host process takes the file-size and the two clocks sequentially, not atomically. No inference about clock synchronization, device latency or sound correctness follows solely from these small gaps.

## Implementation and independent verification

- `tools/audit_nexium_stage327_clock_gap.py` requires the original Stage326 receipt's exact schema, success verdict, distinct pinned original CSV SHA-256 digests, preserved strict Stage304/305 evidence-scope flags, canonical three-event/two-interval order, and integer arithmetic consistency.
- `tests/test_audit_nexium_stage327_clock_gap.py` has ten positive/negative test methods. Synthetic source tampering, false original provenance, non-positive timing, altered event order, and forged inter-cohort delta are rejected. A **positive but suspiciously diverging wall clock** is flagged diagnostically, not mistaken for an audible audio defect.
- `.github/workflows/stage327-original-host-clock-gap.yml` independently downloads the **original already-successful Stage326 source-derived artifact** from run 39168578569; it does not create fake NeXium observations. The first Stage327 [CI run 39169201417](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39169201417) **passed all ten tests and reproduced all four original discrepancies**.
- The new exact-schema negative guard was added after that first success. Any newer CI run of that source version must also be checked before claiming the extra change has passed.

The published Stage327 artifact `stage327-original-host-clock-gap` contains only source SHA-256 digests, event labels and signed host-clock interval differences. It contains **no original PCM, game source data, absolute host clock epochs, guest clock evidence, music or keys**.

## Evidence boundary

Successful Stage327 proves source-bound *host clock accounting* for two original NeXium captures, not the temporal relationship of their host observations to guest music service calls or real hardware audio. The historical archived Stage304 failure remains separate. The full original Stage304/305 PCM chain was successfully audited in the original NeXium runs, not independently rerun within Stage327.
