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
The previously emitted report didn't include exact frame offsets, so why
the pages were separated could not be determined from the JSON alone.

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
