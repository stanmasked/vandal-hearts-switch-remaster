# Vandal Hearts Remake — Stage301: hypothetical scene-marker timing envelopes

Stage300 associates exact-zero *recorded* stereo PCM frames with five
approximate NeXium scene markers. Stage301 preserves those results and
adds a **descriptive sensitivity check**, not a dropout diagnosis.

## Source-bound process

1. Rerun Stage299 from the two original virtual PCM recordings, pinned
   JSON reports and CSV scene-event markers; require exact equality with
   the Stage299 receipt.
2. Rerun Stage300 from those same sources; require exact equality with
   the previous Stage300 JSON.
3. Scan the original scene PCM bytes independently as 4-byte s16le
   stereo frames. Reject changed SHA-256, run count, longest zero run,
   per-zone boundaries, source zero frames, >=100ms zero frames and
   counts of intersections with Stage300 zones.
4. For each original approximate host marker, count source zero frames
   within **hypothetical** windows of +/-250ms, +/-500ms and +/-1000ms
   (clamped to the recording boundaries). Account separately for
   frames inside/outside the disjoint union of five windows, long-run
   zero frames and distinct original runs touched.
5. Check exact frame conservation and monotonic window inclusion. The
   envelopes cannot overlap given Stage300's validated scene spacing.

Emulator smoke output:
`runtime-evidence/pcm-marker-envelopes-stage301.json`

Tests:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_pcm_marker_uncertainty.py' -v`

## Interpretation limits

The envelope sizes are deliberately selected **what-if parameters**.
They are *not* measured marker timing errors or statistically justified
confidence intervals. Host snapshots of a buffered recorder do not
provide sample-accurate guest music transition times or audio queue
service timestamps.

An exact-zero PCM frame is not a verified dropped frame. This experiment
does not identify original-game soundtrack bytes, real Switch DAC output,
human-audible defects, underruns, or scene-change causality. No audio
engine, PCM generation, audout implementation or game assets are changed.
