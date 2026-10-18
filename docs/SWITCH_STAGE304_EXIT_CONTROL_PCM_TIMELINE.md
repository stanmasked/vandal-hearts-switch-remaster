# Vandal Hearts Remake — Stage304: host Plus exit controls versus virtual PCM silence

## Question

Stage302 measured an exact-zero virtual PCM run reaching the end of
the scene recording. Stage303 captures the original recorder file size
immediately before SIGINT and after waiting for `parec`. Stage304 adds
**actual host-side input control snapshots** to help distinguish frames
already present around the test application's exit action from frames
recorded later. This is a source-bound descriptive audit, **not** a proof
of when game music stopped.

## How the evidence is captured

The existing optical exit sequence holds controller X and sends Plus
using NeXium's actual `xdotool` key events. The host scene capture
script now writes `scene-exit-controls.csv` with three distinct event
names, buffered PCM byte-length snapshots, and host epoch milliseconds:

1. `before_plus_down`: snapshot just before the actual Plus keydown.
2. `after_plus_up`: snapshot just after actual Plus release.
3. `control_sequence_end`: snapshot after optical screenshot,
   controller release and the existing three-second settling interval.

It neither inserts fake guest audio markers nor changes the existing
optical exit command. The original virtual recorder runs continuously
through the sequence and its stop lifecycle (Stage303) is separate.

## Independent audit

`tools/audit_nexium_pcm_exit_controls.py` first recomputes and
strictly compares Stage299–303 evidence against the same original PCM.
The new audit rejects malformed/noncanonical source event CSV,
reordered/duplicate events, reversed timestamps, nonmonotone host PCM
file sizes, controls predating the last scene marker or extending past
the original recorder SIGINT snapshot, and changed source hashes.

For each event, it intersects the *original trailing exact-zero run*
with the observed buffered PCM byte count. Non-frame-aligned snapshots
yield **minimum and maximum** observable frame bounds (never a
fabricated fractional-frame timestamp).

Output:
`runtime-evidence/pcm-exit-controls-stage304.json`.

Host regression suite:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_pcm_exit_controls.py' -v`.

## Interpretation boundary

The raw file byte count is a *buffered host snapshot*, not a guest
sample-exact timing source. X/Plus input cannot be assumed to cause the
zero run; independent guest audio callbacks, real Nintendo Switch
hardware DAC, original retail soundtrack, physical speaker output,
and audibly defective playback have **not** been verified.

No synthesizer, music data, SPU or audout implementation was changed.
