# Vandal Hearts Remake — Stage332: original guest-software source stability frontier

Stages 328–331 independently replayed two actual successful NeXium original guest `audoutPlayBuffer` software histories from source-authentic archival artifacts. Stage330 classified deletion of one among the fifteen calls preceding the last successful call, and Stage331 classified all 105 unordered **pair** omissions. Neither stage measures speakers, DAC or guest-to-host PCM sample timing.

Stage332 calculates the **complete source-verified sensitivity frontier for zero through three deletions** of the previous fifteen normal guest software calls, always leaving the original final normal successful call untouched:

| Deleted earlier software calls | Original earlier software calls retained | Number of combinations in each original capture |
| --- | ---: | ---: |
| 0 | 15 | 1 |
| 1 | 14 | 15 |
| 2 | 13 | 105 |
| 3 | 12 | 455 |

Each capture contributes exactly **576 deterministic source subsets**, not 576 new or independent runs. The independent script `tools/audit_nexium_stage332_original_playbuffer_frontier.py` checks all four original CSV SHA-256 pins, runs the Stage328–331 auditors again, and requires the previously verified one- and two-deletion median/MAD/rank results to be exactly reproduced before reporting the three-deletion frontier.

The resulting compact receipt describes each deletion level's lower-median minimum, maximum, range; median absolute deviation minimum/maximum; last call's first-possible rank interval and subset counts with last call shorter than, equal to, or longer than the remaining earlier-call median. It reports the earliest **observed** instability within k=0..3 but explicitly does not extrapolate robustness beyond three omissions.

Twelve positive/negative regression tests cover uniform and nonuniform real-source-compatible previous-call tails, a synthetic first instability at k=3, ties, source tampering, identical fake cohorts and guest-time privacy boundaries. An independent CI workflow `.github/workflows/stage332-original-playbuffer-frontier.yml` fetches the two exact originally successful NeXium source archives.

**Not a physical audio test:** These subset statistics are a retrospective sensitivity analysis of bounded guest **software-call service durations**. They are not a population confidence interval, 576 independent samples, original PS1 soundtrack fidelity proof, an acoustic glitch diagnosis or Switch speaker timing. No audio generation, SPU, PCM, guest sound scheduling, `audoutPlayBuffer` or original strict Stage304/305 code changes are required. Until its independent workflow succeeds, actual original three-deletion medians and ranks remain unconfirmed.
