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
