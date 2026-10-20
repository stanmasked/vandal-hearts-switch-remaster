# MAP02 virtual 48-kHz sink: exact page positions and gap audit

## Verified baseline (not a continuous-stream claim)

Parent Draft #223 at `759f8414e574194eb21de086b3c25ce9cff56587`
ran the actual opt-in NRO in NeXium. Exact-HEAD [GitHub Actions
#39348805748](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39348805748)
passed all four jobs. The native optical `VHPRE001` witness again reported
**eight unmodified pre-`audoutPlayBuffer` PCM pages**. A *separately recorded*
16.487083-second, 48-kHz stereo s16le virtual PulseAudio monitor had RMS
**500.200519** and **361,758** samples with magnitude ≥256.

Crucially, **each individual 557/558-frame original page occurred exactly once
in the recording, matching BOTH CRC32 and FNV-1a64**:
`per_page_matches=[1,1,1,1,1,1,1,1]`.
But `exact_contiguous_chain_count=0`, so the old report deliberately said
`NO_EXACT_EIGHT_PAGE_SINK_MATCH`. **Do not** interpret that as silence, broken
PCM, a verified speaker output, or a sample-perfect continuous sound stream.
The original first-run JSON did not include exact frame offsets. We have
now downloaded the actual *unexpired* artifact `map02-presubmit-nexium-guest-proof`,
ID `12232810691`, from run `39348805748` and independently checked its
raw PCM against all eight guest page CRC32+FNV64 fingerprints.

### Original capture: independently measured positions

The raw file `presubmit-virtual-sink-s16le-48k.pcm` contains **791,380**
interleaved signed PCM16 stereo frames (3,165,520 bytes), SHA-256:

```
008b925334ba46fb324f16630ee3ee6dd517a21663979700df9eaf4e533827bc
```

`presubmit-guest.json` SHA-256:
`f9bf14061bd3f411879aea639da3e619765c70462377fe83de9745aacada62bf`.
The same-run `manifest.json` identifies `source_sha=759f8414e574194eb21de086b3c25ce9cff56587`,
`run_id=39348805748` and NRO binary SHA-256
`68751097f18c3040268651a7c807c240facf3f289a4355593aa6046541cb9ea0`.

| Guest page index | Exact first stereo frame | Page length | Gap before next |
| --- | ---: | ---: | ---: |
| 0 | 44,550 | 557 | 467 |
| 1 | 45,574 | 557 | 1,491 |
| 2 | 47,622 | 557 | 467 |
| 3 | 48,646 | 558 | 978 |
| 4 | 50,182 | 557 | 979 |
| 5 | 51,718 | 557 | 467 |
| 6 | 52,742 | 557 | 979 |
| 7 | 54,278 | 558 | — |

Observed **page-start increments**:
`[1024, 2048, 1024, 1536, 1536, 1024, 1536]` stereo frames.
All starts are the same phase **6 modulo 512**.
All seven inter-page regions were inspected byte-for-byte and contained
**only zero PCM16 bytes**, totaling **5,828 extra silent stereo frames /
121.416667 ms**. The eight exact pages themselves total **4,458** stereo
frames / **92.875 ms**. This shows a 512-frame start cadence with silent
padding; it **does not identify which component inserts that padding**.
Do not label it audout queue time, physical DAC timing, or proven audio loss
without a separate controlled experiment.

## This child experiment

Adds **read-only diagnostics** to `tools/audit_presubmit_virtual_sink.py`:

- `unique_page_frame_offsets` — exact first-frame positions in one raw
  same-run 48-kHz virtual monitor for each of the eight guest pages, or
  `null` if the page is absent or ambiguous.
- `all_eight_pages_found_once` and `unique_page_order_preserved` —
  distinguish eight exact unique matches in order from duplicates/reordering.
- `inter_page_gap_frames[i]` = source frame offset of page i+1 **minus**
  (offset of page i + frames of page i). **Positive** means extra monitor
  frames between complete, exact pages; zero means contiguous; **negative**
  means overlapping/reordered spans. These are observed distances, not
  guessed causes or physical DAC/driver queue latency.
- `inter_page_gap_ms` converts the signed gap counts at exactly 48 kHz;
  `total_positive_gap_frames` sums only positive gaps.
- `all_pages_contiguous_in_order` is true only for one unique matching
  page in each position, monotone offsets and zero gaps.

Added generated-only tests for exact continuous pages, synthetic extra frames
at seven boundaries (13,0,128,0,7,0,23), inverted page order and a
missing/damaged frame. All findings remain **virtual sink** observations.

## Acceptance

The child CI must run the *identical previous optical & virtual monitor
capture workflow* with newly instrumented **Python-only** analyzer.
Read the uploaded `presubmit-sink-parity.json` rather than relying on a
green GitHub Actions badge: a green capture may still report incomplete
continuity. If unique pages stay in order with positive gaps, compare gap
sizes to libnx buffer-queue or SDL/PulseAudio processing periods in a separate
narrow experiment. If pages are reordered, investigate multiple sink inputs
and guest-session chronology before drawing conclusions. Do **not** edit
game PCM generation or suppress the original strict CRC/FNV verifier.

No original PS1 audio assets, no switch loudspeaker or physical-DAC claims.
Preserve Draft #218, Draft #223 and `main`. **Draft / DO NOT MERGE.**
