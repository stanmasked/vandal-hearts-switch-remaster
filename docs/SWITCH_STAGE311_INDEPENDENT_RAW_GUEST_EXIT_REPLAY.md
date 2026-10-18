# Vandal Hearts Remake — Stage311: independently replay the archived original guest exit source

## Purpose

Stage310 added the byte-exact, original **guest-created** `audio-exit-timeline-000.csv` to the NeXium runtime artifact. The source was verified against the original guest SD mount, the guest monotonic exit receipt (Stage307), and CRC-verified optical music scenes (Stage308).

Stage311 closes a separate provenance question: **can an independent runner validate the archived original bytes itself** rather than merely accepting the capture-time Stage310 JSON attestation?

## Independent replay

The new workflow
`.github/workflows/stage311-original-guest-exit-archive.yml`
checks out the source decoders on a new GitHub Actions runner and
downloads `nexium-runtime-evidence` from the exact original Stage310
NeXium workflow run **39141325435**. It requires five files to
exist exactly once within one runtime evidence directory:

- `audio-exit-timeline-000.csv` — original guest-created, five-row CSV
- `scene-optical-trace.png` — original post-join guest framebuffer source
- `guest-audio-exit-timeline-stage307.json`
- `guest-optical-exit-clock-stage308.json`
- `guest-original-exit-source-stage310.json`

The independent `tools/replay_nexium_original_guest_exit_archive.py`
rejects missing, duplicate, symlinked or disconnected evidence files.

It reads the raw original CSV again, recomputes canonical guest event
names, monotonic timestamps and **SHA-256**, and regenerates the exact
Stage307 report. It independently re-decodes the original optical PNG,
validates the guest payload CRC32, all four musical scene transitions
and the software time ordering, and regenerates the exact Stage308
report. Finally, it recomputes the Stage310 original source
preservation receipt from the raw source and optical results and
requires exact equality.

Only independently recomputed measurements are uploaded as
`independent-stage311-evidence/original-guest-exit-stage311.json`.
The new workflow artifact does not duplicate the source PCM, retail
files or original image.

## Negative controls

`tests/test_replay_nexium_original_guest_exit_archive.py`
includes 13 tests for malformed raw source, tampered Stage307–310
receipts, swapped optical PNG, missing or duplicate original CSV,
symlinked input, disconnected receipt directory, invalid source run
identifier and non-audible claim preservation.

## Evidence boundaries

The Stage311 report can prove that the actual guest CSV bytes were
re-audited in a **separate workflow**. It cannot prove that those guest
timestamps are synchronized to host PulseAudio PCM file-size samples,
audout DAC output, physical Nintendo Switch speakers, or any original
retail soundtrack. It does not modify synthesizer SPU, audio output,
game logic, the diagnostic capture or the user's game assets.
