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
