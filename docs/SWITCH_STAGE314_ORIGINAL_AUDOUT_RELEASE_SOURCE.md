# Vandal Hearts Remake — Stage314: archive original guest audout page-return CSV

## Context

Stage313 adds two distinct, *guest-software* audio observations without
changing the synthesizer or audout service behavior: the timestamp/frame
count of the last successfully returned original PCM buffer, and the
attempt/result of the already-existing bounded normal-exit taper.
That measurement is not a speaker or DAC sound timestamp.

Stage310 and Stage311 already proved the model for preserving and
independently replaying the **original, guest-created** exit timeline
file: no reconstructed CSV from JSON, and no hidden raw bytes.

## Stage314 source preservation

`tools/preserve_nexium_guest_last_buffer_original.py` rereads the
original isolated NeXium guest SD root, and requires these sources:

- Original `audio-exit-timeline-000.csv` from the guest, with canonical
  ordered, guest-monotonic software timestamps.
- The identical original exit timeline preserved by Stage310 in
  `runtime-evidence/audio-exit-timeline-000.csv`.
- Stage307 guest exit receipt and Stage310 original source SHA/size
  receipts, reproduced against the real original bytes.
- Original guest `audio-exit-output-000.csv` from Stage313, and the
  exact independently reproduced Stage313 source report.

Only after checking all of these, Stage314 copies the **unmodified
guest-created page-return CSV** into
`runtime-evidence/audio-exit-output-000.csv` by exclusive creation
and verifies the bytes after copying.

It emits the independent source receipt
`runtime-evidence/guest-original-audout-last-page-stage314.json`,
including source SHA-256, size, last-return timing relative to in-game
observed Plus, and explicit limitations. The NeXium job now requires
the original source to exist and pass all guards before the job can
report full success.

The preexisting `runtime-evidence/` artifact upload includes both
the Stage313 raw guest source and Stage314 SHA witness. These sources
are **five software-telemetry rows**, not game tracks, original
PlayStation assets, PCM audio, BIOS files, or console secrets.

## Negative tests

`tests/test_preserve_nexium_guest_last_buffer_original.py` has 12
tests including exact source byte round-trip, source SHA matching,
guest exit mismatches, altered Stage307/310/313 receipts, replaced
guest source content, missing or symlinked original page CSV,
ambiguous multiple guest SD files, exclusive output protection,
determinism, and rejection of audible/hardware claims.

Run:
`python3 -m unittest discover -s tests -p 'test_preserve_nexium_guest_last_buffer_original.py' -v`.

The Host SPU test workflow and real NeXium smoke now run these checks
alongside Stage313.

## Interpretation

The timestamp of a returned audout buffer tells us when the guest
audio owner regained that buffer after a service call, not when any
sample passed a DAC or reached the listener. The optional 2 ms exit
taper is not original PS1 synthesized music. There is still no
calibrated mapping from this guest software clock to host PulseAudio
buffer snapshots or the last source PCM zero sample.

Stage314 is a source-provenance change only; it makes no changes to
gameplay, sample generation, SPU, sound queues, or the existing
normal-exit teardown.
