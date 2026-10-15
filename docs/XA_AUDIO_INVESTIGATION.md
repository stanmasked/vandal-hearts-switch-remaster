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
