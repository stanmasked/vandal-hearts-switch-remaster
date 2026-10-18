# Vandal Hearts Remake — Stage302: recorded PCM edge censoring

Stage301 confirmed exact-source digital silence around five **approximate**
host-side music-scene marker locations, at three hypothetical ± radii.
Stage302 asks a different question: did the original zero run **touch
the beginning or end of the recording**, or did nonzero PCM frames exist
on both sides?

## Logic

- Independently replay Stage299, Stage300 and Stage301 source evidence.
- Rescan original scene PCM as s16le stereo frames; count exact-zero runs.
- Classify each original run exactly once into one of four categories:
  `whole_recording`, `recording_start`, `interior`, `recording_end`.
  A completely zero recording is **not** counted as both prefix and EOF.
- Count zero frames, run counts and ≥100ms runs independently for
  each classification, with exact conservation.
- Verify SHA-256 and the complete original Stage300 top-20 longest-run
  **start, end, length and seconds**, not just the totals.
- Record whether the final exact-zero run begins after the last
  **approximate** host marker; this is source alignment only.

Runtime report:
`runtime-evidence/pcm-recording-edge-silence-stage302.json`.

Synthetic test:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_pcm_terminal_silence.py' -v`

## Evidence limits

"Recording end" means the final observed **virtual capture frame**.
It does NOT prove that the game, composer, SPU, audio queue, NeXium
output, or expected soundtrack ended there. EOF may be an artifact of
how and when the host capture was stopped. Internal runs also cannot
by themselves identify any audible defect. These tools do not measure
physical Nintendo Switch audio, original retail soundtrack identity,
guest-accurate scene times or causal transitions. No audio synthesis,
audout behavior, or game assets are modified.
