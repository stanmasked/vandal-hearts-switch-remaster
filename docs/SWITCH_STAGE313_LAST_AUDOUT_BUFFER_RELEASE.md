# Vandal Hearts Remake — Stage313: last returned guest audout PCM page

## Motivation

Three original NeXium guest software shutdowns (Stages 307–312) now
describe Plus observed, requested audio stop, worker cleanup, audout
close, and joined worker, and Stage311 has independently replayed the
original guest-created CSV bytes. However, an **audout service close**
timestamp is not an actual last PCM buffer return timestamp, and
neither is evidence of speaker playback or a musical defect.

Stage313 adds a separate diagnostic witness of the last successfully
released audout PCM page within the guest application. This is the
earliest way to compare exit software events to the final audio
producer page on the *same guest monotonic software clock*.

## Bounded guest witness

`source/vh_audio_exit_output_witness.h` has a fixed-size C11 atomic
witness with the following fields:

- `page_return_count` — successful original PCM pages returned to
  the audio owner, **not** lower-level audoutPlayBuffer attempts.
- `last_page_return_guest_ns` — most recent successful original PCM
  page return, in the same `armTicksToNs(armGetSystemTick())` guest
  software timebase as Stage307.
- `last_page_frames` — number of original 48-kHz stereo frames in
  that returned page, **not** audible delivered frames.
- `tail_attempt_guest_ns` — attempt to submit the optional bounded
  2-ms normal-exit last-sample-to-zero taper after worker cleanup.
- `tail_success_return_guest_ns` — bounded taper descriptor release
  success, if any.

All writes are to atomics by the sole audio worker. No file I/O,
allocation or mutex is introduced in the PCM path; all file export
occurs **after thread join**. The original Stage307 five-row
`audio-exit-timeline-000.csv` stays byte-compatible.

The new independent optional guest file is
`sdmc:/switch/vandal-hearts-remake/audio-exit-output-000.csv`.
Numbered exclusive file creation ensures that no earlier diagnostic
record is overwritten. Failure to write this optional diagnostic
file never changes application shutdown outcome.

## Audit

`tools/audit_nexium_guest_last_buffer_return.py` independently
reads the original guest SD source and the original guest exit
milestones, checks canonical counters and chronological constraints,
and classifies the last returned page relative to **guest observed
Plus, stop request and worker cleanup**. Missing SD transport is
`GUEST_LAST_AUDOUT_RELEASE_NOT_OBSERVED`, not a fabricated success.

The NeXium smoke workflow requires an actual guest source, and
writes `runtime-evidence/guest-last-audout-release-stage313.json`.
Current evidence is **not** a host PCM ↔ guest clock calibration.
No direct relationship to the final host-captured digital-zero PCM
sample can be inferred without a shared sampling/timing reference.

## Tests

- C11 GCC and Clang `tests/test_vh_audio_exit_output_witness.c`.
- 11 Python source and chronology tests
  `tests/test_audit_nexium_guest_last_buffer_return.py`.
- Existing Host SPU regression suite and full NeXium NRO smoke test.

## Interpretation boundaries

A successful `audout` buffer *return* means that the audio owner
regained its buffer lease. It does **not** certify PCM passed through
the output queue to physical DAC or speakers, an audible playback
endpoint, the original PS1 soundtrack, or a defect caused by Plus.

No synthesized SPU material, frame scheduling, music assets, sound
format, user data, or gameplay flow is modified.
