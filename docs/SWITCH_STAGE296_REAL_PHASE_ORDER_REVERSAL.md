# Vandal Hearts Remake — Stage296: measured 0→8 then 8→0 source-verified sessions

Stages294–295 compiled two distinct NROs with phases 0 and 8,
captured real `audoutGetAudioOutBufferCount` service snapshots
every 16 submitted calls, and verified the original guest SD CSVs.
Stage295 found ALL ZERO pre-submit service queue counts in its own
two NeXium sessions but different ≥40ms call counts on sampled calls.
The order was always normal phase0, experimental phase8.

## Stage296 reversed second pair

Without increasing polling frequency, modifying the synthesizer,
changing the audio worker, or relabeling old NRO/SD evidence,
the NeXium workflow runs four independent scene-switch sessions:

1. phase0 baseline (existing independently audited original SD);
2. phase8 experiment (existing independently audited original SD);
3. **phase8 again** — a distinct fresh original guest SD and CSV;
4. **phase0 again** — another distinct fresh original guest SD and CSV.

The two additional captures reuse the exact baseline and phase8 NRO
SHA-256 identities from the same current workflow attempt.
They run in isolated NeXium guest roots ending `-phase8r` and
`-phase0r`. Each guest scene CSV is checked against its
independent copied original before any service probe audit.

Each new phase-specific `audit_nexium_audout_service_probes.py`
requires the correct exact attempt sequence, real original SD,
byte-exact copy, writer receipt, independent queue/latency/slow/clock
counters, original guest event INPUT timestamps and **zero overflow**.

Finally `tools/audit_nexium_phase_order_reversal.py` checks:
- four independent original SD hashes and verified ten real
  music-changing INPUTs each;
- exactly ordered guest-reported query attempts and counts for
  phases 0,8,8,0;
- identical current-run SHA-256 NRO pair and GitHub run provenance
  across the two reported phase pairs;
- successful/failed query counts, real zero/nonzero buffer counts,
  and overlap with ≥40/≥50ms slow calls;
- phase0 minus phase8 per-1,000 queried calls in the first and
  reversed pair, and their difference.

Four sequential guest sessions are NOT randomized or simultaneous
and do not control changes in host load. Each capture has its OWN
guest clock. Neither pre-submit service count nor call-duration
statistics can prove causality, audio scheduler behavior, DAC
underrun, audible correctness or physical Nintendo Switch output.

## Confirmed corrected Stage296 original-SD result — 18 October 2026

[Successful four-session NeXium CI 39123296150](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39123296150)
completed on source commit
[`4bf526b4`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/4bf526b4a72d04b5f230dd531ff35976e809ac52).

The complete original guest-SD audit confirmed:

| Real service sample | 0 first | 8 first | 8 reversed | 0 reversed |
| --- | ---: | ---: | ---: | ---: |
| Total queries | 122 | 121 | 120 | 120 |
| >=40ms calls ON queried attempts | 1 | 1 | 1 | 0 |
| Nonzero service buffer-count results | 0 | 0 | 0 | 0 |

All **483** actual pre-submit queue queries returned zero. There was
no dropped service sample; each source was authenticated as a separate
current-run original guest SD. The phase0-minus-phase8 normalized
sampled >=40ms software API call rate was **−0.067741 per 1,000
queried calls** in the first ordered pair and **−8.333333** in the
reversed pair. These are descriptive contrasts across separate runs,
not time-paired observations, randomization, evidence of
audio-device starvation or a causal effect of the query phase.

The preceding run [39122469138](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39122469138)
had failed because the legacy parser incorrectly assumed a phase0
sample on the partial final group of a phase8 capture.
The fix and explicit regression are in `4bf526b4`, and the entire
workflow then passed. No changes to synthesizer, PCM generation,
SPU or physical-device behavior were made.
