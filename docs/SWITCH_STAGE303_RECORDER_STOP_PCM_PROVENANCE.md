# Vandal Hearts Remake — Stage303: recorder-stop source provenance

Stage302 observed an original NeXium virtual PCM capture containing a long
zero run at its **recording boundary**. Stage303 records two new host-side
facts to distinguish already-recorded frames from bytes appended while the
virtual PulseAudio monitor recorder is being stopped.

## Recorded source

`tools/capture_nexium_scene_audio.sh` writes a new two-row
`scene-recorder-stop.csv` from the actual recorder process:

- `before_sigint`: host epoch (milliseconds) and `stat` file byte count
  immediately before requesting `SIGINT` from `parec`.
- `after_wait`: host epoch and file byte count after waiting for that
  same recorder process.

Both rows record whether sending `SIGINT` succeeded. Unsuccessful signal,
missing rows, noncanonical unsigned decimals, reversed timestamps,
shrinking file, impossible final length or changed source PCM fail closed.

The independent Stage303 analyzer reruns Stage299, Stage300, Stage301 and
Stage302 against the *same recorded files* before accepting the new CSV.
For a terminal exact-zero run ending at PCM EOF, it partitions frames
relative to the recorder stop snapshot. If the pre-signal byte count is
not divisible by four bytes per stereo frame, it returns **min/max
bounds**, not an invented exact frame timestamp.

Report: `runtime-evidence/pcm-recorder-stop-stage303.json`.
Host regression suite:
`python3 -m unittest discover -s tests -p 'test_audit_nexium_pcm_recorder_stop.py' -v`.

## Limits

A byte-length `stat` is a snapshot of a buffered host file, not a
guest-time audio sample counter. A successful `SIGINT` to `parec`
does **not** establish when guest synthesis stopped, whether queue
underruns occurred, the original soundtrack identity, or human-audible
quality. Neither Nintendo Switch DAC nor physical speakers are measured.
This is a diagnostic boundary classification, not an audible error gate.
No synthesis code, audout semantics or copyrighted retail assets changed.
