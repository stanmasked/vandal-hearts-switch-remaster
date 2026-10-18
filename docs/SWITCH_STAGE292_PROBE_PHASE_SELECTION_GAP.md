# Vandal Hearts Remake — Stage292: measured 1-in-16 phase vs all calls

The Stage291 independent [NeXium CI 39116833050](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39116833050)
**passed**, checking 16 deterministic attempt-index sampling phases
against BOTH original same-NRO guest-SD traces and revalidating Stage290.
It observed 12 positive and 4 negative ≥40ms switching-minus-idle
phase contrasts; the actual service-count query used only phase 0.
The current Stage291 **source run is different from Stage290**.
Never substitute earlier runs' counts.

The key remaining question is whether the actually measured pre-submit
queue phase (attempts 1,17,33,...) has the same slow-call frequency
as the entire stream. It need not: the sample is systematic and the
16 alternative slow-call phase results have widely varying values.

## Exact arithmetic, one original source

`tools/analyze_nexium_phase_selection_gap.py` re-opens each original
current-workflow guest SD slow/latency/clock/queue source; reruns the
complete Stage291 audit and checks the regenerated JSON byte-for-byte
as an object against the current Stage291 report. No source NRO or
capture operation is changed.

For each mode and class (≥40ms, nonoverlapping 40..<50ms and ≥50ms)
it calculates with exact `Fraction` values:

- Actual phase 0 duration-class count / actual phase 0 attempts;
- Full duration-class count / **all** audout attempts;
- Measured phase 0 minus all-calls normalized rates;
- The same three contrasts between switching and idle;
- The exact weighted 16-phase identity: the sum of each phase
  rate multiplied by its known attempt denominator equals the
  total slow-call count expressed per 1,000 attempts.

This disambiguates the *sampling discrepancy* from a real whole-stream
slow-call difference. The terms are descriptive and **not estimator
bias**, given deterministic sampling and no randomized design.
Queue service counts for phases 1..15 have never been measured, so
they remain absent. No new audio is captured.

To verify on an ORIGINAL same-NRO guest SD in NeXium:

```sh
python3 tools/analyze_nexium_phase_selection_gap.py \
  --switch-sd-root "$RUNNER_TEMP/vh-nexium-stage268-$GITHUB_RUN_ID" \
  --idle-sd-root "$RUNNER_TEMP/vh-nexium-idle276-$GITHUB_RUN_ID" \
  --switch-evidence runtime-evidence/scene-soak \
  --idle-evidence runtime-evidence/idle-control \
  --stage290-report runtime-evidence/idle-control/idle-switch-service-probe-comparison.json \
  --stage291-report runtime-evidence/idle-control/idle-switch-phase-sensitivity.json \
  --switch-slow-report runtime-evidence/scene-soak/soak-audout-exact-slow-verification.json \
  --idle-verdict runtime-evidence/idle-control/idle-audout-verification.json \
  --output runtime-evidence/idle-control/idle-switch-phase-selection-gap.json
```

This explicitly does **not** measure physical Switch output,
OS scheduler callbacks, actual DAC queue behavior or audible glitches.
Capture order remains switching before idle, and the alternative
phases are partitions of the SAME original calls, not independent
replications.
