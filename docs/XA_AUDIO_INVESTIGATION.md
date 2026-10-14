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
