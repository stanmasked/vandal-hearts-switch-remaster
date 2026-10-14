# PS1 STR video restoration utility

The helper at `tools/restore_ps1_str.py` is an experimental workflow for an **already extracted** PlayStation STR stream. It does not extract files from a BIN/CUE image or from an archive, and it has not yet been validated against a Vandal Hearts cutscene.

## 1. Inspect an extracted stream safely

Use Python 3; inspection does not require FFmpeg and does not create an output file:

```sh
python3 tools/restore_ps1_str.py /path/to/extracted-video.STR --inspect-only
```

The report includes the file size, the number of complete 2048-byte sectors, and the number of sectors beginning with the STR tag currently recognized by the script. A zero count is a diagnostic clue, not definitive proof that the file is not a video: different extraction layouts may need different handling.

## 2. Attempt restoration

The encode mode requires an FFmpeg build that supports the `psxstr` demuxer and the relevant MDEC decoding path:

```sh
python3 tools/restore_ps1_str.py /path/to/extracted-video.STR \
  --output ./restored-video.mp4
```

Optional controls:

- `--width` and `--height`: output dimensions (default 960×720).
- `--crf`: H.264 quality setting from 0 to 51 (default 17; lower is higher quality).
- `--keep-intermediate`: retain the repacked intermediate stream for troubleshooting.

The script refuses empty input, non-sector-aligned input, and identical input/output paths. Keep the original extracted file unchanged and work on a copy.

## Current limitations

- Input must be a raw extraction laid out as 2048-byte sectors; a complete disc image is not accepted directly.
- Reconstructing 2352-byte sectors is currently a heuristic. The script synthesizes sector headers and identifies candidate video sectors using a simple tag check. That may not match every extraction or STR variant.
- Passing the inspection step only confirms basic structural clues. It does **not** prove that FFmpeg can demux or decode the stream.
- No real Vandal Hearts STR sample has yet been used to confirm end-to-end video restoration. Synthetic unit tests validate sector accounting and safety checks only.
- Do not commit disc images, ROMs, or copyrighted game assets to this public repository. Keep any legally obtained extracted resources local.

## Tests

Run the utility's host-side tests with:

```sh
python3 tests/test_restore_ps1_str.py
```

The repository CI also runs these tests as part of `make test`.
