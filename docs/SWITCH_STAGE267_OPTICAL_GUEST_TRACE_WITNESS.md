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

## End-to-end result — native guest event trace recovered

The corrected [NeXium run 39053160279](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39053160279) **completed SUCCESS** on exact workflow code SHA `e3506b12b864bd6e4828828b8a9561f3444d7266`. Its build and emulator jobs passed, including all six optical-decoder negative/positive tests, the existing graphics/input probes, stereo PCM, two FIELD/FOCUS cycles and the actual screenshot-to-CSV gate. The guest NRO is still the separately pinned build SHA `5a50433fb52d905cee074de052820895566143bf` and SHA-256 `58a438082f282ba279044d2a25fc1369e8493571a67b2082da41e0d8c0405929`.

Original runtime evidence was downloaded from GitHub Actions artifact **`12108642272`**, `nexium-runtime-evidence`, ZIP SHA-256 `0bafd5c3b20d2c9978668efdb503ddcf9ad26dbd2db28797fc8273a596e3beb3`. All ZIP CRC entries were valid. The evidence includes original `scene-optical-trace.png`, `guest-optical-trace.csv`, `guest-scene-trace.csv`, independent audio and visual screenshots, and machine reports.

**Unexpected but verified additional result:** the isolated NeXium SD export succeeded **in this run too**, even though it was unavailable in Stage 266. The SD verdict is `FOUR_GUEST_SCENE_INTERNAL_PHASES_OBSERVED`, and the file is `audio-scene-trace-0000.csv`. The reason for this change of behavior has **not** been isolated. Do not attribute it to a particular NeXium filesystem fix or the X+Plus exit sequence without a controlled separate test. The stderr transport remained **`GUEST_TRACE_NOT_OBSERVED`**.

An independent container-side decoder was written separately from the repository decoder and run against the published **real** 1280×720 screenshot, then compared **byte for byte** against both the optical-derived and SD-exported CSVs. Verified geometry: magenta border `(264,154)-(1032,612)`; exact 7,392-bit payload recovered; packet SHA-256 `eb00eb1e3be2e9916ddcec5f3a47afc0db737b7aeae0254e0bdb252c2bcc5c80`; CRC32 `d2e3bdbb` (computed and declared match); **23** events, **0** dropped, 3 startup events with serial 0; exact 726-byte canonical CSV SHA-256 `5f64dbbc5f2d93bdd8fb45fbfad2813ace473d36508839305c83162d99c4622d`. Both transmission paths yielded identical bytes.

### Internal guest-observed timings (milliseconds)

| Transition | INPUT→ACCEPT | INPUT→RELEASE_RETURN | SUBMIT_CALL→RELEASE_RETURN |
| --- | ---: | ---: | ---: |
| FOCUS 1 | 17.560 | 33.788 | 15.562 |
| FIELD 1 | 13.556 | 48.880 | 34.933 |
| FOCUS 2 | 32.092 | 64.547 | 32.127 |
| FIELD 2 | 15.791 | 49.074 | 32.933 |

All four serials have ordered `INPUT`, `POST`, `ACCEPT`, `SUBMIT_CALL` and `RELEASE_RETURN` events. These **are internal event intervals reported by guest software**, observed under emulator scheduling. They are neither host keyboard event-to-sample-onset latency nor real Switch hardware/DAC/speaker latency. The submitted buffer may hold audio generated before the scene change; `RELEASE_RETURN` is not playback-start time. There is no evidence here of physical undistorted music or absence of hardware underruns.

The optical decoder's first successful run reused the strict SD-CSV parser and gave its nested auditor a misleading `source` label implying SD readback even when analyzing pixels. Follow-up code commit `bf8cfcac023ae7ca2169745c04d493ab5a9d18c5` explicitly labels the nested auditor as **framebuffer-derived**, leaving any independent SD verification to the separate SD verdict. The original archived evidence bytes have **not** been modified or rewritten.

**Final Stage 267 conclusion: `GUEST_INTERNAL_AUDIO_SCENE_TIMESTAMPS_RECOVERED` in NeXium; physical Switch remains `HARDWARE NOT TESTED`.**

## Second independent full emulator confirmation

After the transport-provenance label correction, [NeXium run 39053726025](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39053726025) on source SHA `bf8cfcac023ae7ca2169745c04d493ab5a9d18c5` also completed **SUCCESS** in both jobs. Its published original runtime evidence artifact **`12109125395`** was downloaded independently; ZIP SHA-256 `17c1b4e064a1fe164eae5a1808a6f7f9eb22fa3edec70e607b4bd5aa7d8cc8c7`; **41 files with no ZIP CRC errors**.

A separate clean decode of the second screenshot's actual 7,392 pixel bits recovered a **different genuine guest session**, rather than reusing the first one's CSV:
- Second optical packet SHA-256 `cfb0742495869d48f068813307e297397e2a51b951eee96979e316f4a43a094e`, CRC32 `fca3ca31`.
- **23 guest events, 0 dropped**, including the same four complete alternating scene serials and three unattributed startup events.
- Second optical CSV SHA-256 `305e6d436f9fa8eb6840c76b10e706848372f2ca72e9f8fd3cb37e73395228e4`, **728 bytes**.
- The **second SD-exported CSV matches the second optical CSV byte for byte**. The two run hashes intentionally differ; this rules out accidentally substituting a stale first-run capture for the second run's proof.
- Nested optical audit source now correctly states `reconstructed from CRC-verified guest framebuffer pixels`, not an SD readback claim.

| Internal guest interval (ms) | Run 39053160279 INPUT→ACCEPT | Run 39053726025 INPUT→ACCEPT | Second INPUT→RELEASE_RETURN |
| --- | ---: | ---: | ---: |
| FOCUS 1 | 17.560 | 16.609 | 50.780 |
| FIELD 1 | 13.556 | 11.435 | 47.229 |
| FOCUS 2 | 32.092 | 31.420 | 65.126 |
| FIELD 2 | 15.791 | 4.392 | 20.627 |

**Result:** two independent emulator sessions successfully transmitted *their own distinct* guest event logs by both visual framebuffer pixels and the emulated SD filesystem. The exact reason SD was absent in Stage 266 is still unknown; these positive observations do not prove physical FAT durability. Actual Switch hardware, speaker output, HOME/sleep, retail soundtrack and input-to-DAC latency remain **`HARDWARE NOT TESTED`**.

The documentation-only changes following those two successful CI runs do not retroactively change the pinned NRO or the runner code SHAs.
