# Vandal Hearts Remake — Stage333: original guest-software call median reversal boundary

Stage332 independently confirmed [CI #39174200226](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39174200226) that **both authentic original NeXium captures** retained a final successful `audoutPlayBuffer` guest software call below the median of every previous-call subset formed by omitting zero, one, two, or three of the fifteen preceding calls.

In the second source, the most sensitive three-deletion median (22,369,896 guest software ns) was just **17,396 ns above** the unchanged final call (22,352,500 ns). Rather than continuing arbitrary k-by-k sensitivity updates, Stage333 answers a finite, source-bounded question: **What is the first number of deleted earlier calls that allows a remaining lower median no greater than the final software-call duration?**

The analyzer `tools/audit_nexium_stage333_original_playbuffer_reversal_threshold.py` first replays the complete source-authenticated Stage328–332 audit chain from two genuinely successful NeXium archives and all four pinned original CSV SHA-256 digests. It then enumerates exactly **1 + 15 + 105 + 455 + 1,365 + 3,003 = 4,944** different omissions with k=0..5 in **each** original capture, retaining the untouched final call. For every k it publishes the minimum and maximum previous-call-median-minus-final **guest software** margin and counts strict shorter, equal or longer outcomes.

If the final call is strictly shorter than the minimum of *every* earlier call in the retained original sixteen-call window, a purely finite-set implication proves it is also shorter than the median of **every nonempty subset** of those prior calls. This proof applies **only to the captured window**, not unobserved guest service calls or physical audio. For less separated cohorts, exhaustive 0..5 enumeration determines the first possible reversal within that tested range; no population confidence interval is inferred.

Twelve synthetic positive/negative tests cover the guaranteed-all-subsets case, five faster/ten slower prior calls with a first k=5 reversal, exact k=5 combination accounting, ties, tampered Stage320/322 source evidence and source privacy. The dedicated GitHub Actions workflow `.github/workflows/stage333-original-playbuffer-reversal.yml` downloads the original artifacts and recomputes the result. Stage333 is a natural endpoint for retrospective sensitivity analysis on these two fixed source samples; further meaningful audio confidence will need **additional independent live capture runs** or physical hardware playback evidence.

**Limits:** All durations are guest *software service call* brackets, not host PCM sample times, DAC output, speaker latency, preserved PS1 retail soundtrack proof, plus-induced audio failure or real Nintendo Switch hardware measurements. Stage304/305, SPU, audout, PCM and gameplay remain unchanged. ### Verified independent original-source result

[Stage333 GitHub Actions #39174673214](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39174673214) **completed successfully**, passing 12/12 synthetic source and negative-control tests and downloading both actual archived NeXium capture artifacts.

| Source-audited finite guest-software comparison | First NeXium | Second NeXium |
| --- | ---: | ---: |
| Prior original calls shorter/equal/longer than last | 0 / 0 / 15 | 5 / 0 / 10 |
| First deletion level with a subset whose median is not greater than last | None for any nonempty subset (proved) | **5** |
| For k=5, subsets where last is shorter than median | 3,003 / 3,003 | 2,751 / 3,003 |
| For k=5, subsets where last is equal to median | 0 | 0 |
| For k=5, subsets where last is longer than median | 0 | **252 / 3,003** |
| Smallest k=5 previous-median minus final software margin | +20,467,501 ns | −3,324,479 ns |

This *closes this retrospective finite-source sensitivity exercise*. The first capture's exact strict inequality is mathematically preserved by any nonempty subset of its original previous calls, whereas the second source reaches an observed reversal at five deleted earlier calls. The 4,944 inspected subsets per source are **not independently performed game sessions**. New genuine NeXium captures, not more resampling of these two frozen windows, are required for additional independent software evidence.
