# Stage 267 — optical guest-audio trace witness (experimental)

**Scope:** recover actual post-join libnx guest event timestamps in the
NeXium emulator without relying on guest stderr or partially implemented
`sdmc:` write support. Hardware Switch acceptance remains
**`HARDWARE NOT TESTED`**.

## Code and separation of responsibilities

- `source/vh_audio_scene_optical.[ch]`: after the audio worker is stopped
  and joined, a bounded 64-event atomic trace is encoded as a fixed
  924-byte payload and rendered once as black/white framebuffer modules.
  No audio render callback, per-frame loop or mailbox request performs
  image formatting, file operations or sleeps.
- `source/main.c`: visual transport is **opt-in** on an exit where Plus
  is pressed while X is held. Normal Plus-only exit is unchanged. In
  diagnostic mode, the rendered frame remains visible for five seconds
  and is then closed. This temporary delay is **not** an audout delay
  measurement.
- `tools/capture_nexium_scene_audio.sh`: the established two-cycle
  A/B music-scene test now presses NeXium's configured X and Plus keys
  (V and M) together, then captures
  `runtime-evidence/scene-optical-trace.png` from the **actual** emulator
  window. The SD receipt remains independently recorded.
- `tools/decode_nexium_guest_trace_frame.py`: uses calibration-color
  pixel positions, not OCR or timestamp interpolation, to recover bits.
  The exact payload must have valid reserved zeros, event counts, CRC32
  and guest event rows. It invokes the existing scene/serial auditor and
  can require four complete alternating FIELD/FOCUS transitions.
- `tests/test_vh_audio_scene_optical.c`: 924-byte packet tests, reference
  CRC, 7,392 independently checked pixel bits, fixed marker positions,
  bounds and event-capacity saturation.
- `tests/test_decode_nexium_guest_trace_frame.py`: clean receipt,
  NeXium-like nearest-neighbor resize, damaged pixel/CRC, malformed
  marker and false-or-incomplete scene-transition negatives.

## Exact binary protocol

| Field | Bytes | Encoding |
| --- | ---: | --- |
| Magic/version | 8 | ASCII `VHFBTRC1` |
| Emitted rows | 1 | unsigned 0..64 |
| Dropped event count | 4 | little-endian unsigned |
| 64 event slots | 896 | 14 bytes each: kind u8, scene u8, serial LE32, guest monotonic ns LE64 |
| CRC32 | 4 | IEEE/reflected CRC32 of the initial 909 bytes |
| Reserved | 11 | all-zero; failure if changed |

Exactly 924 bytes equals 7,392 bits in a 112-column × 66-row matrix.
Each cell spans 7×7 native framebuffer pixels; a bright magenta
one-cell calibration border is 798×476 guest pixels, anchored at
(250,160). The decoder locates the border by color and rescales
sampling centers to match the actual emulator screenshot crop.

The encoded guest nanosecond readings are **not** physical HID press
timestamps, DAC output timestamps or speaker sound-onset times.
`SUBMIT_CALL` is before the audout buffer-return operation;
`RELEASE_RETURN` reflects its successful return, not acoustic output.
Serial zero denotes an unmatched/ambiguous mailbox receipt. Full
64-slot saturation includes an explicit dropped count and cannot be
treated as a complete record.

## Preflight and CI boundary

- Integrated optical NRO build: [GitHub Actions 39052705390](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39052705390),
  code SHA `5a50433fb52d905cee074de052820895566143bf`,
  **SUCCESS**. Artifact `12108202456`,
  archive SHA-256
  `4996023dc000d5a900cdb343b9bd3cd9956cab53e39e1cac103804cc2ca2a483`.
- NRO extracted independently: **274,488 bytes**, SHA-256
  `58a438082f282ba279044d2a25fc1369e8493571a67b2082da41e0d8c0405929`;
  GitHub receipt and real ZIP bytes match, and both ZIP members pass CRC.
- First optical decoder CI attempt
  [39052965503](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39052965503):
  **FAILED** in one negative synthetic test; the fixture accidentally
  reused the original scene value. Five other decoder tests passed, and
  the primary native build job passed. The negative fixture was corrected
  in commit `e3506b12b864bd6e4828828b8a9561f3444d7266`.
- The corrected end-to-end workflow is
  [39053160279](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39053160279).
  Its **final CI status and actual optical screenshot must be
  independently checked** before reporting that guest timestamps have
  been recovered.

The SD exporter remains available for a future hardware test.
NeXium's absence of guest SD output and stderr in earlier stages is
not reinterpreted as a valid zero-duration event. If the optical
decoder fails, a screenshot is only diagnostic evidence of failure,
not a confirmed guest timeline. Hardware remains **HARDWARE NOT TESTED**.
