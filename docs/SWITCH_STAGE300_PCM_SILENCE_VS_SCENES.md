# Vandal Hearts Remake — Stage300: digital silence and approximate music-scene markers

After [successful Stage299 NeXium workflow 39127993232](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39127993232),
the previous raw virtual PCM evidence was SHA-256-bound and audited.
The separate 48-kHz stereo A/B scene recording contained 1,461
exact-zero runs, including a longest run of 5.839875 seconds.
Those values **do not themselves prove a dropout**.

Stage300 adds `tools/analyze_nexium_pcm_scene_silence.py`. The tool:
- Reruns the ENTIRE prior Stage299 monitor + scene capture source
  analysis and demands full equality with that current-run JSON.
- Checks the raw scene PCM SHA-256, total frames, every original
  exact-zero stereo run, count and longest run against Stage299.
- Binds each of the five scene markers to actual source event CSV
  records and their pre-existing scene-audio report.
- Partitions the whole PCM timeline into disjoint zones:
  before the first marker, a 1.5-s **post-marker guard**, an
  independently previously accepted **settled scene** region,
  and a 0.5-s **pre-next-marker or recording-end guard**.
- Accounts for every frame of every exact-zero run across these zones,
  including runs that straddle markers or guards. It reports
  ≥100ms zero runs separately and the 20 longest runs with their
  frame-precise zone overlaps.
- Rejects any mismatch in observed PCM counts, zones, host scene
  markers or previously reported SHA-256 hashes.

The CI output is
`runtime-evidence/pcm-scene-silence-stage300.json`.

**Critical scope:** scene offsets are host-side `stat` snapshots
of a buffered recorder after button interactions, not precise guest
music callback timestamps. The "settled" window is a descriptive
indexing convention, NOT proof of audio correct/incorrect state.
An exact-zero segment may be intentional or may reflect renderer
startup or virtual monitor conditions. No independent per-frame
timestamps, true original soundtrack PCM reference, real Nintendo
Switch DAC, physically audible sound or event-caused underflow
has been established. Threshold crossings are **not** defect gates.

This stage modifies neither synthesizer nor audout implementation.

## Verified Stage300 NeXium source results — 18 October 2026

The complete [same-commit NeXium run **39129407196**](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39129407196)
finished **SUCCESS** on
[`3757a37b`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/3757a37b1559980faece0c30461afd6682cb7714).
The workflow executed the full source-reconstruction of Stage299 from
**both current-run raw virtual PCM recordings**, checked their
previous SHA-256 reports, five original buffered scene markers,
all exact zero stereo frame counts, and the exact five-scene
zone partition.

The actual source-bound Stage300 stdout recorded:

- **Two** exact-zero stereo runs of at least **100ms**.
- Longest exact-zero run: **281,836 frames** = **5.871583s**
  at 48,000 frames/second.
- The longest run's exact zone overlap:
  **257,836 frames (5.371583s)** inside
  `field_2:settled_scene`; **24,000 frames (0.5s)** inside
  `field_2:pre_next_or_end_guard`.
- These parts sum *exactly* to **281,836** frames and
  **do not cross** a scene marker. All scene-interval and
  whole-PCM frame accounting checks passed.

Unlike the Stage299 measurement of 5.839875s, this is a
**different current-run recording**; both numbers represent
their own independent virtual PCM sources and should not be
mistaken for mismatched reports.

**Interpretation limitations:** most of this longest exact-zero run
occurred while the source was inside the **nominal settled region
of the last field scene**, according to a host-buffered PCM
byte-offset marker. This narrows down *where* the zero signal was
recorded. It does **not** prove that the game should have been
playing continuously at this point, that a button event caused
silence, or that any guest audio DAC was starved. A host-side
source recording and marker offsets cannot prove a dropout
without an independent expected audio timeline.

All on-commit checks passed:
[Host C/Python + toolchain 39129407207](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39129407207),
[Host SPU 39129407192](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39129407192),
[native PCM 39129407174](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39129407174),
and [full NRO/NeXium 39129407196](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39129407196).
