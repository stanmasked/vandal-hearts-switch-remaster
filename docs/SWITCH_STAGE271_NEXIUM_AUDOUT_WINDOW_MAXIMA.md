# Switch Stage 271 — NeXium per-second audout call maxima

**Status:** offline analysis of previously successful guest SD captures. **HARDWARE NOT TESTED.**

The new tool \`tools/analyze_nexium_audout_window_maxima.py\` reads two or
more actual GitHub Actions evidence ZIPs, first applying the independent
Stage-270 same-NRO + scene + guest-audout CSV/receipt verifiers and
requiring the two runs to have distinct workflow/attempt IDs. It then
derives a frequency **of per-second maximum call durations**, not a
histogram or percentile distribution of individual \`audoutPlayBuffer\`
calls. Every source window and its submit count is kept in the JSON output.

## Observed baseline

The successful runs of identical NRO bytes
(\`60dc486339331de6c5d24f6e2b049c8ba24ee095a8534746af9f42d18a8a1b91\`)
yield the following independently derived CSV statistics:

| Guest per-second maximum | [Run 39065603152](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39065603152) | [Run 39065671551](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39065671551) |
| --- | ---: | ---: |
| Guest seconds sampled | 53 | 53 |
| Total actual audout attempts | 1,930 | 1,925 |
| Median second-window maximum (nearest rank) | 37.190 ms | 36.147 ms |
| P90 second-window maximum (nearest rank) | 48.948 ms | 50.363 ms |
| Global greatest call-duration observation | 49.765 ms | 51.692 ms |
| Windows with maximum 40–<50 ms | 21 | 11 |
| Windows with maximum ≥50 ms | 0 | 7 |
| Windows with maximum 25–<40 ms | 32 | 35 |
| Seconds where a ≥50 ms maximum occurred | none | 0, 18, 21, 23, 29, 43, 46 |
| Failed submits / clock anomalies / evicted windows | 0 / 0 / 0 | 0 / 0 / 0 |

Each window has many submitted and released pages, but the old Stage-269
CSV stores **only the greatest** blocking call per second. Therefore a
window with a maximum ≥50 ms proves *at least one* call reached that
duration, **not** how many calls in that window were slow. A P90 of
window maxima **must not be labelled P90 latency across all calls**.
Likewise, no queue pre-submit sample establishes a continuous device
playback buffer level. Different maxima can reflect host scheduling and
emulator conditions.

## Tooling and confidence boundaries

The stage-271 analyzer requires Stage-270 validation of:
- exactly the same NRO hash across unique CI runs, bound to each
  run's own manifest and scene audit;
- the canonical per-second guest CSV, original/copy hashes,
  independent successful producer receipt, and matching guest audit;
- exact per-window seconds, sum of submitted pages and the recorded
  whole-session maximum; no window evictions or guest clock errors.

The analyzer rejects truncated, altered or duplicated evidence using
the Stage-270 validator and does not silently accept mismatched NROs.
Negative controls specifically check distorted window ordering,
altered CSV, duplicate runs, wrong executable and absent artifacts.

\`\`\`sh
python3 tools/analyze_nexium_audout_window_maxima.py \
  --artifact stage270-success-run-39065603152.zip \
  --artifact stage270-success-run-39065671551.zip \
  --output stage271-window-maxima.json
\`\`\`

Only archival **copies** are available after workflow completion;
\`original_guest_sd_reopened_after_actions_run=false\` is explicit. The
original guest SD was separately and successfully verified in each
original CI job, whose reports are inside those artifacts. The saved
reference report is \`vandal_hearts_stage271_audout_window_maxima.json\`.

**What this does NOT show:** an actual count of calls above 40/50 ms,
true audio queue occupancy, true DAC underruns, audible defects,
console scheduler performance, or behavior on a physical Nintendo Switch.
For such claims, a future separately versioned per-call aggregate
counter should be added to the *real guest* PCM-thread telemetry, without
overloading the existing Stage-269 original audout CSV schema.
