# Vandal Hearts Remake — Stage284: paired leave-one-out by temporal boundary

Stage283's [successful eight-pair independent CI
39082987951](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39082987951)
reported the following **≥40 ms blocking audout API-call temporal
contrasts**, per 1,000 calls, between two 17-second windows:

| Boundary shift | Earlier−later switch-minus-idle contrast |
| ---: | ---: |
| −4 s | +4.889043 |
| −3 s | +4.550673 |
| −2 s | +3.726928 |
| −1 s | +2.886552 |
| 0 s | +4.431099 |

Every pooled contrast is positive, but these are overlapping
retrospective virtualized guest-software observations. Neither they
nor the Stage282 result establish audible glitches or a causal
scene-switch effect.

## Further Stage284 robustness audit

The Stage284 `tools/analyze_nexium_steady_boundary_pair_grid.py`
takes all Stage279–283 source reports **regenerated in the same CI
job** from the eight original-SD-bound archives. It runs the exact
Stage283 analysis again and refuses any mismatch with the supplied
Stage283 report. For each of five shifts and each 40/50 ms threshold:

1. Reconstructs the actual 17-second per-mode per-pair numerators and
   denominators from original verified per-second counters.
2. Separately reports the *switching* and the *idle* rate drift between
   early and late 17-second windows. Their difference must exactly
   reconcile the Stage283 pooled time contrast.
3. Omits each source workflow pair in turn from **both** modes and
   **both** time windows, reporting all eight exclusion outcomes,
   not only their range. Revalidates extrema against Stage283.
4. Produces a complete 5-shift × 8-deleted-pair grid and its count
   of positive, negative, or exactly tied contrasts, without assuming
   the same sign in advance or selecting a favorable boundary.
5. Preserves immutable source run IDs, NRO identity, fixed capture
   order and the Stage279–283 no-hardware/no-causal scope.

Running the analysis after the four upstream reports:

```sh
python3 tools/analyze_nexium_steady_boundary_pair_grid.py \
  --verified-steady-state verified-pairs/steady-state-only-s1-to-s51.json \
  --verified-temporal-thirds verified-pairs/steady-state-three-17s-segments.json \
  --verified-third-sensitivity verified-pairs/steady-state-three-17s-sensitivity.json \
  --verified-temporal-contrasts verified-pairs/steady-state-temporal-contrasts.json \
  --verified-boundary-shifts verified-pairs/steady-state-fixed-left-boundary-shifts.json \
  --output verified-pairs/steady-state-boundary-pair-grid.json
```

Six host synthetic regressions cover reproducibility, altered
subsecond counters, altered prior reports, mismatched pair identity,
different mode denominators, and physical/causal-claim exclusions.

This is a descriptive **influence/sensitivity matrix**, not a
randomized effect estimate, multiple independent replicates, an
inferential confidence interval, or a physical Nintendo Switch
listening test. The original emulator runs always used switching
before idle, so age/order and host effects remain possible
confounders. No original copyrighted game audio is included.
