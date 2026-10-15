# CD-XA audio resource investigation

## Confirmed observations

The extracted ISO9660 entry `STR_US/XA_STR1.;1` maps to LBA 19469 in the raw BIN image and has a size of 227,475,456 bytes (111,072 2048-byte payload blocks). Comparing the first 64 payload bytes against the extracted file confirmed that the ISO extraction corresponds to the bytes in the raw image after the 24-byte raw-sector header.

A separate inspection of all 111,072 raw 2352-byte sectors at that LBA range reported:

- Valid 12-byte sync patterns and Mode 2 in every sector.
- Matching duplicated XA subheaders in every sector.
- 101,359 sectors with submode `0x64` (audio, Form 2, realtime).
- 9,704 sectors with submode `0x00`, eight with `0xE4`, and one with `0x80`.
- Typical XA subheader bytes `01 00 64 01` repeated twice. Coding byte `0x01` indicates stereo, 37.8 kHz, 4-bit ADPCM under the CD-XA format.

These observations strongly support that this resource contains CD-XA ADPCM sectors. They do **not** yet establish a successful audio decode, synchronization, or listening validation.

## Important extraction detail

An ISO file extracted as 2048-byte blocks does not retain the full raw-sector layout or all 2324 bytes of a Mode 2 Form 2 sector payload. Audio recovery therefore needs to read the original 2352-byte sectors and parse the duplicated XA subheader and sector submode, rather than feeding the 2048-byte extraction to the existing video repacker.

Do not infer audio properties from the filename alone. Filter candidate audio sectors using their raw-sector metadata, preserve their order and timing, and validate any decoder output by checking duration and listening for continuity before describing audio restoration as complete.

## Next validation steps

1. Re-run the sector scan against the legally obtained local BIN and confirm the exact LBA range and subheader counts.
2. Determine how non-audio sectors and any gaps affect stream timing.
3. Test a documented CD-XA ADPCM decoder on the selected raw-sector payloads.
4. Inspect the output with FFprobe and listen for continuity, pitch, channel layout, and duration.
5. Keep source disc data and extracted copyrighted resources local; do not commit them to this public repository.

Reference format documentation: [PSX-SPX CD-ROM format](https://psx-spx.consoledev.net/dev/ps1/cdr/cdromformat/) and [CD-ROM streaming formats](https://psx-spx.consoledev.net/dev/ps1/cdr/cdromfileformats/streaming/).


## Repository inspection helper

The repository now includes a read-only metadata inspector for raw 2352-byte sectors:

```sh
python3 tools/inspect_cdxa.py /path/to/local-disc-image.bin
```

It reports sync-pattern, Mode 2, duplicated-subheader, XA audio and Form 2 audio counts, plus submode/coding-info distributions. Synthetic tests cover valid audio metadata, mismatched subheaders, non-Mode-2 sectors, empty input, and invalid sector alignment. The helper does **not** decode ADPCM or write audio files. Run it on a local, legally obtained raw BIN; do not upload the disc image to the public repository.

To focus on the `XA_STR1.` file range in the full BIN, pass its start LBA and sector count. The currently documented range is 111,072 raw sectors starting at LBA 19469:

```sh
python3 tools/inspect_cdxa.py /path/to/local-disc-image.bin --start-lba 19469 --sector-count 111072
```

The range options are bounds-checked; they do not alter the input image. Use them to compare a targeted scan with the previously recorded counts before attempting any audio extraction.

## Payload extraction helper

A separate helper now extracts the 2304-byte sound-group area from each sector whose duplicated subheader identifies Mode 2 Form 2 XA audio. The 2324-byte Form 2 user-data area includes 20 trailing bytes that are not part of the 18 × 128-byte XA sound groups; the extractor deliberately excludes that padding. It supports LBA ranges and optional XA file/channel filters, and can write a JSON report:

```sh
python3 tools/extract_cdxa_payload.py /path/to/local-disc-image.bin ./xa-payload.bin \
  --start-lba 19469 --sector-count 111072 --report ./xa-report.json
```

The output is an intermediate compressed-data stream containing XA sound groups, **not a playable WAV**. The helper skips non-audio sectors and records non-contiguous audio-sector transitions; those transitions may represent timing gaps, so do not assume that concatenation alone preserves original playback timing. It never overwrites the source image. Keep output files local if they contain copyrighted game data.


## Experimental decoder profile and compatibility notes

`tools/decode_cdxa_adpcm.py` currently implements the common 4-bit stereo, 37.8 kHz profile only. It validates the duplicated parameter headers and rejects filter indices outside 0–3 and raw shift nibbles above 12 rather than silently interpreting malformed or unusual headers.

This strict policy is intentional for the first validation pass: it makes suspicious sectors visible instead of quietly changing their meaning. It differs from some playback decoders, including vgmstream, which warn about shift nibbles above 12 and substitute a fallback shift of 9. If a real local dump contains such values, record their sector/group offsets first; then decide whether a separate permissive compatibility mode is warranted. Do not weaken strict validation globally based only on another decoder's fallback behavior.

Predictor history is currently kept unclipped while the emitted signed 16-bit PCM is clamped. Decoder implementations differ on history clipping and integer rounding, so this is a documented implementation choice rather than proof of bit-exact equivalence with every PlayStation CD-XA decoder. The synthetic tests verify this implementation's recurrence, layout, WAV format, and extraction-to-decoding plumbing; they do not replace comparison against a trusted reference vector or listening to a local game dump.


## Safe local extraction-to-WAV validation

The extractor selects XA audio/Form 2 sectors, while the current experimental decoder only supports coding byte `0x01` (4-bit stereo at 37.8 kHz). Before decoding a local disc image, verify that the extraction report contains no other coding-byte values. Keep the BIN, payload, report, and WAV on your own machine; do not commit them.

Example for the documented resource range:

```sh
python3 tools/extract_cdxa_payload.py /path/to/local-disc-image.bin ./xa-payload.bin \
  --start-lba 19469 --sector-count 111072 --report ./xa-report.json

# Continue only if every extracted audio sector uses the decoder's supported profile.
jq -e '(.coding_info_counts | keys) == ["0x01"]' ./xa-report.json

python3 tools/decode_cdxa_adpcm.py ./xa-payload.bin ./xa-restored.wav --extracted-groups
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,bits_per_sample,duration \
  -of default=noprint_wrappers=1 ./xa-restored.wav
```

The `jq` command exits unsuccessfully if the report contains any coding byte other than `0x01`; do not proceed to decode in that case. Review the report's LBA list and non-contiguous transitions before judging duration or continuity: the current payload stream concatenates selected sectors and does not reconstruct missing-sector timing. Finally listen to the WAV and check channel balance, pitch, clicks, gaps, and duration. A valid WAV header and successful decode are necessary checks, not proof of faithful restoration.


## First real-disc validation: bounded sample, not a full encode

Before processing the entire XA resource, validate a short local sector window.
For example, the following scans 256 raw sectors from the previously documented
starting LBA. This is only a starting point, not a confirmed single continuous
audio channel:

```sh
python3 tools/inspect_cdxa.py /path/to/local-disc-image.bin --start-lba 19469 --sector-count 256
python3 tools/extract_cdxa_payload.py /path/to/local-disc-image.bin ./xa-sample.bin \
  --start-lba 19469 --sector-count 256 --file-number 1 --channel 0 --report ./xa-sample.json
python3 tools/validate_cdxa_extraction.py ./xa-sample.json ./xa-sample.bin
python3 tools/decode_cdxa_adpcm.py ./xa-sample.bin ./xa-sample.wav --extracted-groups
python3 tools/validate_cdxa_extraction.py ./xa-sample.json ./xa-sample.bin --wav ./xa-sample.wav
ffprobe -v error -show_entries stream=sample_rate,channels,duration -of default=noprint_wrappers=1 ./xa-sample.wav
```

The sample must be **listened to**, not just checked for valid WAV structure.
Verify the chosen file/channel combination from the report; it may be absent
or may contain unrelated/interleaved material. The extractor intentionally
concatenates qualifying sectors and does **not** reconstruct CD playback timing.

For the supported decoder profile each selected XA sector yields **2016 stereo
sample frames**, so the decoded WAV duration is
`audio_form2_sectors_written * 2016 / 37800` seconds. This is the duration
of concatenated decoded frames, **not necessarily disc playback duration**.
At CD speed, 75 raw sectors pass per second and XA channels may be interleaved;
using the raw LBA span as WAV duration is therefore also incorrect.

If audio contains clicks, silence, pitch errors, or discontinuities, do not
label it restored. Keep the source BIN and resulting payload/WAV local and
record only non-copyrighted diagnostics (counts, channel, coding information,
LBA gaps, decode errors) in the repository.


### Read-only report/payload consistency check

Use `tools/validate_cdxa_extraction.py` before decoding any extracted stream.
It verifies the compressed payload length against sector counts, ensures all
selected sectors use the currently supported `0x01` coding profile, checks
ordered LBA-to-offset mappings and reported gaps, and prints the expected
PCM frame count and concatenated-WAV duration. This check does not inspect
ADPCM sample quality or guarantee correct playback timing. It does not alter
source, report, or payload files.
\nThe optional `--wav` validator checks stereo 16-bit PCM at 37,800 Hz, the exact expected frame count, and truncated PCM data in bounded-size chunks. It does not prove the samples sound correct.\n

### Bind the extraction report to its payload

New extraction reports contain `payload_sha256`, calculated while writing
selected 2304-byte sound groups. The read-only validator independently hashes
the payload and rejects a mismatch, including a different file with the same
size. Reports produced before this field was introduced need to be regenerated
from the local raw BIN; the validator intentionally fails closed when the hash
is missing. The SHA-256 check protects against accidental file/report mix-ups,
but it does not establish that ADPCM was decoded correctly or that LBA timing
was reconstructed.


### Prevent accidental mixing of CD-XA streams

A disc resource may interleave different CD-XA file numbers or channels.
Concatenating their sectors and sharing one ADPCM predictor history can
produce clicks and discontinuities even when every sound group is structurally
valid. New extraction reports include `file_channel_counts` such as
`{"1:0": 123}`; the read-only validator now rejects reports containing
multiple file/channel identities, even when the coding byte is uniform.
Use `--file-number` and `--channel` on the extractor to isolate one stream
and regenerate both the payload and report. The report is diagnostic metadata
only; even a single stream does not prove correct timing or sound quality.
Legacy reports without `file_channel_counts` must be regenerated locally.


### Inspect decoded sector-boundary discontinuities

After extracting **one** file/channel stream, validating its report and
decoding to WAV, the following read-only tool reports PCM amplitude jumps
between the final stereo frame of one selected XA sector and the first stereo
frame of the next:

```sh
python3 tools/analyze_cdxa_boundaries.py ./xa-sample.json ./xa-sample.bin \
  ./xa-sample.wav --threshold 8192 --top 10
```

The report lists the largest sector-boundary jumps, source LBAs, and skipped
raw sectors. The threshold is measured in 16-bit PCM amplitude units; it is
a *diagnostic threshold*, not an objective click detector. Natural transients,
interleaving, intentional silence, and a discontinuous capture range can all
produce jumps. Conversely, codec artifacts may occur **within** a sector and
will not appear in this boundary-only report. Listen to the source and compare
with a known-good decoder before attributing any discontinuity to decoding.
The analyzer reads but does not alter the WAV, payload, or JSON report.

The boundary report now separates `adjacent_lba_boundaries` from `gapped_lba_boundaries` and counts above-threshold jumps separately for both. A gap in raw sector numbering can reflect normal channel interleaving; do not interpret all gapped transitions as missing audio. Compare adjacent-boundary results independently before diagnosing clicks.

The analyzer also reports `local_neighbor_max_jump` for the two immediate PCM changes flanking each sector seam, and `excess_over_local_neighbors` (the nonnegative difference from the seam jump). A steady PCM ramp may have a large seam jump but zero excess; a sudden step from silence may have high excess. This local comparison is only a heuristic and does not establish a recording defect or faithful PS1 playback.


### Nonzero ADPCM recurrence cross-check

`tests/test_decode_cdxa_adpcm.py` now includes a separate scalar-oracle calculation with nonzero signed nibbles, differing left/right predictor filters, and state carried across two sound groups. The test checks exact PCM output and final predictor history. This independently written arithmetic check is **not** a comparison against a separate CD-XA implementation or captured PlayStation output: both the oracle and decoder can share a mistaken interpretation of the format. A reference-implementation comparison and listening check on locally owned game audio remain required before claiming audio fidelity.


### Algorithm-level comparison with an independent implementation

The test `test_vgmstream_style_reference_subframes_and_history` cross-checks
three synthetic nonzero groups using a channel-first reference procedure
based on [vgmstream's XA decoder](https://github.com/vgmstream/vgmstream/blob/master/src/coding/xa_decoder.c).
It uses signed 16-bit nibble expansion rather than the production decoder's
signed-nibble multiply, and independently advances predictor history between
sound groups. It checks exact stereo PCM and history.

This is a **source-algorithm comparison**, not a claim that vgmstream itself
was executed in CI, nor a bit-exact test against original game audio.
Both implementations may still share format assumptions; a local game sample
and a separately executed trusted decoder remain essential for fidelity.


### Compare our PCM with a separately decoded reference WAV

To compare exactly the same **single-file, single-channel** XA sector selection
decoded by our tool and by an independently run reference decoder, use:

```sh
python3 tools/compare_cdxa_wavs.py ./xa-sample.wav ./reference-decoder.wav --require-exact
```

The read-only comparator requires both WAVs to be uncompressed 16-bit stereo at
37,800 Hz with the same frame count. It reports first different frame, number
of differing stereo frames and channel samples, maximum absolute per-sample
difference, and mean absolute per-sample difference. It streams PCM in bounded
chunks rather than loading entire recordings into memory. With `--require-exact`
it exits unsuccessfully when PCM differs. Do not compare files with different
sector selections, histories, channel mappings, or timing arrangements:
mismatches in those cases do not isolate a decoder bug.

An actual second decoder has **not** been run by this tool: supply a reference
WAV produced separately using the same source and selection. Source game audio
and reference WAVs must remain local; do not commit them to this repository.
Even exact PCM agreement does not independently prove original playback timing.


### Nonzero synthetic end-to-end reference test

The regression `test_end_to_end_nonzero_pcm_matches_independent_expected_wav`
constructs one raw Mode 2 Form 2 XA sector, including nonzero signed
ADPCM nibbles with filter 0 and unit reconstruction scale. It extracts the
sound groups, validates the report and payload digest, decodes to WAV, and
compares its exact PCM against a WAV generated directly from the known
nibble values (without invoking the decoder for expected samples).
This checks the **complete** pipeline on a controlled non-silent vector,
including group order, left/right channel mapping and signed nibble handling.

It does **not** replace testing predictive filters, a third-party decoder
process or original game audio; those remain separate validation gates.


### Predictive ADPCM across sector boundaries

The integration test `test_predictive_adpcm_state_survives_sector_boundary`
builds two adjacent synthetic XA sectors with nonzero 4-bit stereo samples
and filter 1 (coefficient 60/64). An independent scalar recurrence produces
a reference WAV while preserving left/right predictor states across all
sound groups and the **sector boundary**. The test performs extraction,
report validation, WAV decoding, and exact PCM comparison.

This verifies state continuity for one predictive-filter profile on synthetic
data. It does not establish exact hardware equivalence for all filter modes,
resampling, stream timing, or actual Vandal Hearts sound.


### Cross-sector two-tap ADPCM regression

`test_two_tap_predictive_filters_across_sector_boundary` generates two
synthetic raw Mode 2 Form 2 sectors with changing XA predictive filters
2 and 3. A separate scalar calculation follows both predictor taps for
each stereo channel, including group and sector boundaries. Extraction,
metadata validation, ADPCM decoding, and exact comparison against its
generated reference WAV run end to end.

This test adds coverage for the two-coefficient recurrence but does not
substitute for comparing with a separately executed reference decoder or
listening to legally obtained local game audio.


### Verify absolute sector range in extraction reports

The report validator also checks an extractor's optional complete source-range
metadata: `start_lba`, `sectors_scanned`, `first_audio_lba`, and
`last_audio_lba`. If any of these keys is present, all four must be present;
the selected LBAs must fit entirely inside the scanned range, and the
endpoints must agree with `audio_lbas`. Older synthetic reports without
any source-range fields remain accepted, but partial or contradictory metadata
is rejected. This is a **consistency** check, not a verification against the
original disc image.

The validator now strictly requires JSON integers for each `audio_lba_offsets` entry (`lba`, `payload_offset`, and `missing_source_sectors_before`). Values such as `false`, `true`, or `2304.0` are rejected even where Python's normal equality operator would treat them as equal to the expected integer. Regression tests cover these deceptive type substitutions.


### Read-only raw BIN cross-check

When the original 2352-byte-sector BIN is available locally, cross-check
**all selected sectors** against the actual disc bytes rather than trusting
the report alone:

```sh
python3 tools/validate_cdxa_extraction.py ./xa-sample.json ./xa-sample.bin \
  --wav ./xa-sample.wav --source-bin "/local/path/to/your/disc.bin"
```

The optional `--source-bin` mode re-scans the report's declared LBA interval,
checks the duplicated XA subheaders and file/channel selection, requires
the same selected LBA sequence, and compares each 2304-byte payload with
the disc sector at that position. It rejects omitted eligible sectors,
mismatched bytes, unaligned images and out-of-range source intervals.
Verification is read-only and does not upload, copy or publish game assets.
Without `--source-bin`, existing report/payload-only validation still works.
This proves byte-level extraction consistency for that local image, not
correct audio playback or the fidelity of the decoder.

Additional synthetic source-BIN regression cases verify that a malformed duplicated XA subheader, an altered sector mode, an unsupported coding byte, or a source image shorter than its declared LBA range causes verification to fail. Such checks test detection only; they do not verify real game audio decoding or Nintendo Switch playback.

When `--source-bin` is supplied, the validator also independently recomputes the number of Mode 2 sectors and the number with matching duplicated XA subheaders across the declared scan range. Both values must agree with the extractor's `mode2_sectors` and `matching_subheaders` counters. Tests reject forged integer counts and boolean lookalikes. This additional integrity check is available only with the local raw source; report-only checks cannot independently establish these counts.

Raw-BIN verification now also recomputes the full `submode_counts` histogram from every Mode 2 sector with matching duplicated subheaders in the reported scan interval, and requires an exact match with the extraction report. A regression case deliberately forges the histogram while preserving its total and confirms rejection. This check is only active when `--source-bin` is provided.

A regression also covers verifying a **nonzero starting LBA** with a bounded scan window and interleaved file/channel streams. It asserts that only sectors at absolute LBAs 2 and 4 in a three-sector window are extracted and cross-checked; an otherwise matching target sector just outside the window is intentionally excluded. Altering the report window triggers an independent Mode 2 counter mismatch. This test runs on fully synthetic sectors, not copyrighted game data.

A post-extraction mutation regression retains the exact extraction report and 2304-byte payload, modifies the raw source image in memory, and runs read-only `--source-bin` validation again. Changes in **either selected audio sector** are rejected, while changes only in an unrelated XA channel inside the same scanned range are accepted. Reverting the source bytes restores success. The original report and payload remain byte-for-byte unchanged throughout. This demonstrates detection of subsequent source changes on synthetic input; it does not independently authenticate the original disc image.

Post-extraction source validation now also has synthetic regression cases for changing the **file number or channel** of a previously selected sector, and for promoting an unrelated channel into the selected stream. Each mutation must fail the independently recomputed selected-LBA sequence, even though the extracted audio bytes and report were kept unchanged. Different valid rejections may occur at the first wrong LBA or when the selected sector count is exhausted.


### One-command local CD-XA verification

With your *locally owned* raw 2352-byte-sector disc image and a separately
decoded reference WAV, run the full chain without uploading game content:

```sh
python3 tools/run_cdxa_local_check.py "/local/path/disc.bin" ./xa-audit-result \
  --file-number 1 --channel 0 --start-lba 19469 --sector-count 64 \
  --reference-wav "/local/path/reference.wav"
```

**The file/channel and LBA values above are illustrative, not verified audio
stream addresses**. Choose a confirmed XA stream and scan range for the
specific local image; do not assume the example stream exists.

The output directory must be new; the command refuses to overwrite existing
results. It extracts only the chosen file/channel, verifies each selected
sector against the original BIN, decodes XA sound groups to stereo
16-bit/37.8 kHz WAV, validates the WAV metadata, and compares exact PCM samples
with the separately generated reference. If samples differ, the command fails
and keeps diagnostic files for inspection. Without `--reference-wav`, the
reported status is **decoded_and_source_verified**, *not* proof of audio
fidelity. Independent decoder execution, source selection, synchronization
and listening checks remain separate gates. Original BIN and WAV data must not
be committed to the repository. The command operates only on local files;
no network transfer is performed.

The PCM reference comparator refuses a candidate and reference pointing to the **same filesystem file**, including identical paths, symlink aliases and hard links. A self-comparison can never establish decoder independence. Two separate copies with identical PCM can still compare equal, so ensure the reference is genuinely produced by a separate decoder; exact matching samples alone do not prove its provenance. Synthetic regression coverage checks these aliases.


The WAV comparator now includes `candidate_wav_sha256` and
`reference_wav_sha256` in its JSON result. These fingerprints cover the
**entire input files**, including RIFF headers, not only decoded PCM.
Two WAV containers can therefore have identical decoded samples but different
SHA-256 hashes. The comparator still uses exact PCM samples for
`exact_match`. Record these hashes along with the independent decoder
name/version and stream parameters when auditing a real local game image.
Hashes establish the bytes compared, **not** independent provenance or
correct audio timing.

The one-command local workflow saves `audit-result.json` in its newly created output directory after a successful decode/source verification and also when a reference PCM comparison reports a mismatch. The JSON records the status, selected LBAs, frame count, and (when compared) full-file SHA-256 fingerprints and first/sample-wise PCM differences. A mismatch still makes the command exit unsuccessfully, but the structured report and WAV remain available for diagnosis. Failures before the comparison stage may not produce an audit JSON; partial extraction outputs remain for inspection. These reports establish what was checked, not the provenance of an independently decoded reference.


### Reference WAV provenance notes

The local runner accepts optional `--reference-decoder "decoder name/version"`
and `--reference-command "command used to generate WAV"` alongside
`--reference-wav`. For example, append those two options to the command
above using the **actual** independent decoder invocation.

When a reference is compared, `audit-result.json` now contains
`reference_provenance`, including supplied decoder identification, command,
and an explicit `user_supplied_not_independently_verified` status. If the
information was not supplied, the fields remain null rather than fabricating
a decoder. Provenance labels without `--reference-wav` are rejected.
This records audit context; the script **does not execute or verify** the
independent reference decoder and cannot certify the claimed origin.

Every successful source-verified local run now includes `payload_sha256` and `decoded_wav_sha256` in `audit-result.json`, even when no reference WAV was provided. These bind an audit to the exact extracted compressed audio bytes and local decoded WAV; when reference comparison is performed, `decoded_wav_sha256` must equal the comparator's `candidate_wav_sha256`. These checksums do not establish decoder accuracy, and the source BIN itself is not hashed by this workflow.


The local audit now records `source_bin_bytes` and `source_bin_sha256`,
computed over the **entire local original BIN** in bounded 1 MiB reads, in
addition to the compressed audio and decoded WAV hashes. This distinguishes
two disc images even if their extracted CD-XA stream matches. The extra full
disc read may take time on large images. Since source verification and hashing
are separate reads, do not modify the original BIN during a run; the tool
does not provide atomic snapshots or cryptographic authentication of the
disc's provenance. Original image bytes remain local and are not uploaded.


### Reverify an existing local audio audit

To check that files still match an earlier run without extracting or decoding
again, use the saved audit JSON and explicitly supply the original BIN:

```sh
python3 tools/verify_cdxa_audit.py ./xa-audit-result/audit-result.json \
  --source-bin "/local/path/disc.bin" \
  --reference-wav "/local/path/reference.wav"
```

Omit `--reference-wav` **only if the original audit had no reference
comparison**. The verifier rehashes the complete BIN, extracted 2304-byte
sector payload and decoded WAV, validates the source sector selection and
WAV layout again, and recomputes the PCM reference comparison where present.
It refuses missing reference WAVs for comparisons already recorded in the
audit. The command is read-only and reports `audit_files_verified` when all
checks pass. A successful result means the current files match the saved,
**user-editable** report; it is not a cryptographic signature, proof of
independent decoding, or proof of audible fidelity. If original output paths
are no longer available, files with matching standard names can be read from
the saved audit's directory.

Saved-audit reverification now also compares the reported `selected_lbas`, `file_number`, `channel`, and `pcm_frames` to the independently validated extraction report and selected-sector count. Changing these audit metadata fields while leaving hashed BIN/payload/WAV files unchanged is rejected. This closes a consistency gap in the earlier audit recheck, but the JSON report is still user-editable and is not digitally signed.

The saved-audit verifier now independently derives the recorded result status from the current WAV comparison. It rejects `exact_reference_pcm_match` on mismatching samples, `reference_pcm_mismatch` on matching samples, and any reference-result status on a source-only audit. A reference comparison must also retain the explicitly **unverified** provenance marker; an unreferenced audit cannot claim reference provenance. The marker is descriptive, not a signature, and no decoder execution is certified.


### Stereo PCM signal diagnostics

The local pipeline now records `pcm_signal_diagnostics` for its decoded WAV:
per-channel absolute peaks, RMS sample amplitude, fraction of zero-valued
samples, number of samples at signed 16-bit extremes, and fraction of frames
where **both** channels are zero. The standalone diagnostic tool is:

```sh
python3 tools/analyze_cdxa_wav_quality.py /local/path/decoded.wav
```

The analyzer reads WAV data in bounded blocks and only accepts uncompressed
stereo 16-bit PCM at 37.8 kHz. The metrics help flag unexpected silence,
unusual levels, or potential clipping for investigation. Neither silence nor
full-scale values are necessarily errors: these statistics do **not** certify
sound quality, XA timing, correct stream selection, or decoder accuracy.
Synthetic tests cover silence, RMS/peaks, full-scale samples, read-chunk
boundaries, and malformed audio.

Saved-audit reverification now **recomputes `pcm_signal_diagnostics`** directly from the decoded WAV and rejects missing or modified peak, RMS, silence, frame and full-scale statistics even if WAV/BIN/payload hashes remain unchanged. This checks report consistency rather than certifying actual CD-XA decoding quality. Reports produced before these diagnostic fields were introduced will fail this newer strict verifier.
