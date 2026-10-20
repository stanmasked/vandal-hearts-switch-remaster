# MAP02: strict virtual sink page-identity gate

**Experimental child of fully green [PR #231](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/231)**, source `33f4ce16cde160d30a154cca453a7545ed106b26`. The eight-page guest `VHPRE001` optical CRC proof and raw virtual 48k stereo monitor are *different proof domains*: one tests PCM before guest audout, the other tests its captured host-sink occurrence.

## Genuine motivation

In [Draft PR #234 exact-head CI #39386868354](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39386868354), *six* real guest jobs completed. The workflow correctly failed overall at `21ms` (two jobs with all-zero PCM and no optical receipt), while the other four guest lanes **passed optical CRC** at `22/23ms`.

Detailed separate same-run virtual-sink PCM reports exposed a **weaker outcome despite green optical jobs**:

| Hint | Guest CRC | Individual source PCM page matches in virtual sink | Nonzero PCM16 samples |
|---|---|---|---:|
| 21ms #1 | FAIL | Not assessable: no guest receipt | 0 |
| 21ms #2 | FAIL | Not assessable | 0 |
| 22ms #1 | PASS | 8/8 pages (unique, ordered) | 521783 |
| 22ms #2 | PASS | **7/8**, page index 6 absent | 493690 |
| 23ms #1 | PASS | **7/8**, page index 2 absent | 522753 |
| 23ms #2 | PASS | 8/8 pages (unique, ordered) | 507852 |

The 7/8 result is *absence of an exact dual CRC32+FNV1a64 complete page in the recorded monitor*; it is **not automatically proof that the guest lost the page or that real Switch hardware dropped sound**. In every lane with multiple matching pages, a **strict full eight-page contiguous chain was not verified** because the host stream inserts PCM16 digital-zero gap intervals. This experiment accepts those *observed* gaps but cannot call the entire stream continuous.

## One strict acceptance change

The new **read-only** `tools/validate_presubmit_sink_eight_pages.py` rejects a guest job that has valid optical CRC but lacks **all eight independently uniquely fingerprinted pages** in its raw virtual monitor.

Checks: per-page match counts exactly `[1]*8`, eight distinct rising frame offsets, known nonoverlapping and PCM16 digital-zero gaps, monitor not all-zero, and agreement between independent monitor frame-count measurements. Fails closed if one page is absent or duplicated, reordered, recorded with nonzero content between expected pages, or monitor health disagrees.

Pure generated-only tests cover the full 8-page positive case with silent gaps and negative cases for page indices **2** and **6**, duplicates, swapped/reordered positions, nonzero gaps, all-zero or truncated monitor, and overlapping offsets.

The GitHub Actions workflow now probes **22ms and 23ms**, two independent runs each, using one same-run source-SHA/NRO-SHA256 pinned research executable. The new strict sink gate runs **after** the existing guest optical and monitor classifier; proof archive uses `if: always()`, so failed lanes remain inspectable.

**An exact 8/8 virtual-sink result is stronger than guest CRC alone but still does not prove continuous audio, original music fidelity, physical Nintendo Switch DAC timing, actual speaker sound or musical cue alignment.**

No guest C code, resampler, DSP, libnx, approved game assets or default production audio changed. [Parent PR #231](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/231) remains frozen and green; [sibling #234](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/234) remains the independent original 21/22/23 evidence. Keep Draft / DO NOT MERGE.
