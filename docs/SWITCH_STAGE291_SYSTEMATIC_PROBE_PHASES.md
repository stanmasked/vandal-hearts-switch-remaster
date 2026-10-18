# Vandal Hearts Remake — Stage291: systematic 1-in-16 phase sensitivity

[Stage290 current-run NeXium workflow
39115937772](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39115937772)
passed. The same NRO's source-original guest-SD verification confirmed
122 queue service probes during switching, 141 during idle, and
six ≥40ms calls on sampled attempts in EACH mode. Every service
query on those sampled attempts returned queue count zero.

**These samples are deterministic:** the native code queries the
pre-submit queue on attempts 1,17,33,..., not a uniformly randomized
subset of all audout calls. Their ≥40ms duration distribution may
therefore be unrepresentative of the full sequence.

## Stage291 independent complete-call accounting

`tools/analyze_nexium_probe_phase_sensitivity.py` independently
reopens the current-run ORIGINAL guest SD files for **both** modes
(verified copy, locations, writer receipts, hashes, clock, per-call
latency and exact ≥40ms call timestamps). It requires that the
previous Stage290 original-SD report matches the identical NRO,
and that the original all-calls counts are conserved.

There are 16 possible call-index residue classes modulo 16:

- Phase **0** (attempts 1,17,33,...) really has SERVICE queue
  observations. Its number of sampled slow calls must agree
  exactly with the actual Stage290 queue-probe report.
- Phases **1–15** have original ≥40ms slow-call durations and
  known all-call denominators, but **NO queue observations**.
  The tool never invents or infers service queue counts there.

The analysis calculates exact integer slow counts, duration bands
and denominators at all 16 phases, then compares the switching and
idle slow-call *rate* within each common phase.

With fixed 1-in-16 sample spacing, the phase difference can
change considerably depending on the selected attempt-index residue.
Phase sweeps are retrospective sensitivity checks over the **same
calls**, not new trials, not confidence intervals and not
independent order-randomized experimental replications.

To re-run on new guest-original SD in the same workflow:

```sh
python3 tools/analyze_nexium_probe_phase_sensitivity.py \
  --switch-sd-root "$RUNNER_TEMP/vh-nexium-stage268-$GITHUB_RUN_ID" \
  --idle-sd-root "$RUNNER_TEMP/vh-nexium-idle276-$GITHUB_RUN_ID" \
  --switch-evidence runtime-evidence/scene-soak \
  --idle-evidence runtime-evidence/idle-control \
  --stage290-report runtime-evidence/idle-control/idle-switch-service-probe-comparison.json \
  --switch-slow-report runtime-evidence/scene-soak/soak-audout-exact-slow-verification.json \
  --idle-verdict runtime-evidence/idle-control/idle-audout-verification.json \
  --output runtime-evidence/idle-control/idle-switch-phase-sensitivity.json
```

A phase result with higher or lower slow-call rate still does
not show OS scheduler behavior, physical Nintendo Switch DAC
underruns, actual audio playback glitches, nor that a soundtrack
INPUT caused the slow call. Switching runs always preceded
idle runs in the workflow.
