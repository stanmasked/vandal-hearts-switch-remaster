# Vandal Hearts Remake — Stage315: independent original audout page-source replay

## Goal

Stage313 introduced a **guest software witness** for the last
successfully released PCM audout buffer and optional bounded normal
exit taper. Stage314 preserves its exact original guest-created
`audio-exit-output-000.csv` source bytes in the NeXium artifact,
cross-checked with Stage307 exit timestamps, preserved Stage310
original guest exit CSV and the Stage313 audit.

Stage315 goes a step further: another GitHub Actions runner downloads
the **complete Stage314 runtime artifact** and independently rereads
both guest-created original sources, rather than trusting the
original-run JSON receipts.

## Inputs and strict source replay

Run `39145082758` is the exact original Stage314 NeXium capture.
The independent source workflow checks that run is **completed
successfully** before downloading its `nexium-runtime-evidence`
artifact. It will fail closed if the producer is incomplete, failed
or cancelled. The source workflow identity is not inferred from
artifact name or file headers.

`tools/replay_nexium_original_audout_exit_archive.py` requires:

- `audio-exit-timeline-000.csv` — original guest-created exit times
- `audio-exit-output-000.csv` — original guest-created last-page witness
- `scene-optical-trace.png` — real CRC-protected guest scene framebuffer
- `guest-audio-exit-timeline-stage307.json`
- `guest-optical-exit-clock-stage308.json`
- `guest-original-exit-source-stage310.json`
- `guest-last-audout-release-stage313.json`
- `guest-original-audout-last-page-stage314.json`

All eight files must appear exactly once and be co-located. The
reader refuses symlinked inputs, duplicates and incomplete archived
sources. It does not reconstruct either original CSV from the saved
JSON.

The independent auditor regenerates and exactly matches original
Stage307, Stage308, Stage310, Stage313 and Stage314 witnesses from
raw source bytes and the CRC-validated optical packet. It recomputes
SHA-256 for both original guest-created CSVs and for the optical PNG.

The result includes the guest software position of the last audout
PCM-buffer lease return relative to **in-game observed Plus**, the
successfully returned page count, and whether the existing optional
bounded 2ms taper was attempted and returned.

Separate-run receipt:
`independent-stage315-evidence/guest-original-last-audout-stage315.json`

The workflow uploads only this independent JSON report, never raw
game music, copyrighted retail files, PCM recordings or console keys.

## Validation and limits

Fourteen synthetic adversarial tests reject substituted original
CSV bytes, altered Stage313 or Stage314 reports, changed optical
frames, missing/duplicated/symlinked files, unconnected directories,
invalid source identity, and attempts to claim audible playback.
The source is validated with the current Pillow-dependent optical
decoder in an isolated test environment.

**Important:** an audout buffer-return event is the guest audio
owner regaining its buffer. It is not a DAC output timestamp,
the last PCM sample played to a speaker, an audible dropout, or
the PS1 retail soundtrack. The guest monotonic clock is not
sample-aligned with host PulseAudio PCM recording buffers. Stage315
does not change SPU, audout, synthesized music, queue scheduling
or gameplay exit behavior.
