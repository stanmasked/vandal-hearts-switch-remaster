# Vandal Hearts Remake — Stage 280: temporal thirds of steady NeXium audout

Stage279 proved an exact, common *relative guest-audio-service-age*
comparison of seconds 1–51 across eight archived NeXium idle/switch
pairs, removing second 0 with its cold-start artifact. This stage
checks whether the overall ≥40 ms software API-call rate difference
is concentrated in a specific portion of those same 51 seconds.

The three **nonoverlapping** intervals are seconds **1–17, 18–34,
and 35–51**. There is no interpolation, missing-second substitution,
or new guest/audio capture. These are 17 audout-clock seconds apiece,
not independently observed loudspeaker timing windows.

The new Stage279 per-second counters are emitted only after the
complete original-SD-bound archived copies, chronological exact
slow-call timestamps, individual duration thresholds and histogram
bucket equality have been checked. Stage280 requires those
revalidated counts and independently enforces:

- Precisely 51 strictly ordered bins for each mode of every distinct
  source workflow run, with nonnegative integer attempts/≥40/≥50
  counters and the expected nested thresholds.
- Per-run 51-second sums equal the existing Stage279 paired summary
  **and** each Stage279 verified mode total.
- All 3 × 17-second segment counts add back exactly to Stage279's
  51-second totals for idle and switching, separately for attempts,
  ≥40 ms calls and ≥50 ms calls.
- Every segment keeps the same NRO SHA-256 and independent run IDs.
  Every segment reports normalized rates using **only its own
  attempted calls**, preserving the complete within-run pair.
- Fail-closed synthetic regressions reject dropped/repeated seconds,
  mismatched bands, impossible counts, fake hardware claims and
  duplicated pair identities.

Run after Stage279 has freshly reaudited the archive inputs:

```sh
python3 tools/analyze_nexium_steady_segments.py \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --output verified-pairs/steady-state-three-17s-segments.json
```

`nexium-eight-pair-variability.yml` produces both reports in **one**
CI execution and publishes them together, along with the eight
source archive SHA-256 values. The Stage280 analyzer consumes the
Stage279 result; an arbitrary standalone JSON input cannot by itself
prove original runner SD file authenticity.

This is *exploratory time-position sensitivity*. Switching always
preceded idle in the existing NeXium workflows. These are blocking
`audoutPlayBuffer` service-call durations, not audible glitches,
DAC underruns, physical Switch behavior or randomized causal evidence.
Do not claim additional measured values or completed Stage280 CI
until the corresponding workflow actually succeeds.
