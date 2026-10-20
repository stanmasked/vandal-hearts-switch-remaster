# Vandal Hearts Remake — Stage331: pair-deletion sensitivity of original PlayBuffer software calls

Stage330 independently verified both genuine NeXium guest-software tails with [CI #39172334832](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39172334832). It tested removal of **one** of the fifteen previous successful `audoutPlayBuffer` calls.

Stage331 extends that question by considering **all 105 unordered pairs** of those same fifteen earlier calls (15 choose 2). Each calculation retains thirteen previous successful software calls and always keeps the original final call untouched. It measures lower-median, MAD, final-call first-possible insertion rank and counts how often the final call is shorter than, equal to or longer than the deletion median.

The auditor `tools/audit_nexium_stage331_original_playbuffer_pair_deletion.py` replays the Stage328–330 strict original source chain using four pinned authentic SHA-256 CSV hashes from the two distinct successful NeXium runs 39166023593 and 39167324026. Its 12 synthetic acceptance/rejection tests verify full pair conservation, nonuniform and tied distributions, sensitivity reversal and source tampering. CI downloads both original artifacts, not constructed PlayBuffer traces.

A rank or last-call/median reversal on deletion of two prior records is **valid sensitivity information**, not grounds to reject an otherwise authentic original capture. The source auditor reports the result rather than suppressing it. The summary does not reveal original guest absolute timestamps or PCM content.

## Confirmed Stage331 real-source results

[Independent CI #39173184454](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39173184454) **passed all 12 synthetic tests** and independently replayed the genuine source files from both original NeXium runs. It examined all 105 pairs of previous-call omissions per source:

| Source-bound software metric | First capture | Second capture |
| --- | ---: | ---: |
| Full previous-15 median | 32,154,011 ns | 31,247,083 ns |
| Previous-13 median after any two deletions: min | 31,803,177 ns | 29,928,490 ns |
| Previous-13 median after any two deletions: max | 32,259,479 ns | 31,632,708 ns |
| Pair-deletion median span | 456,302 ns | 1,704,218 ns |
| Pair-deletion MAD min | 583,906 ns | 3,274,011 ns |
| Pair-deletion MAD max | 1,125,937 ns | 9,262,812 ns |
| Untouched final-call first possible rank range | 1–1 | 4–6 |
| Subsets with final call below earlier-call median | 105/105 | 105/105 |
| Subsets with final call equal to / above median | 0/0 | 0/0 |

The independent [Host SPU CI #39173188973](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39173188973) also passed. These statistics describe software service calls only, not audible effects.

**Evidence limit:** These 105 resamples per cohort are not 105 independent experimental runs, population confidence intervals, guest-host sample clock synchronization, physical Nintendo Switch speaker measurements or proof of a Plus-caused audio defect. SPU synthesis, `audoutPlayBuffer`, PCM, soundtrack, gameplay and strict Stage304/305 behavior are unchanged. Verify the independent Stage331 workflow result before treating computed original rank/median spans as confirmed.
