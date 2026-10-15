# VAB VH structural inspection (read-only)

This repository contains a host-side inspector for Sony PlayStation VAB instrument
headers. It uses synthetic test fixtures; it does not bundle game music or VB
sample data.

## Local usage

```sh
python3 tools/inspect_vab_header.py /local/path/music.vh
python3 tools/inspect_vab_header.py /local/path/music.vh --vb /local/path/music.vb
python3 tests/test_inspect_vab_header.py
python3 tests/test_inspect_vab_sizes.py
```

The first 32 bytes must have the `pBAV` magic. The inspector reports header
metadata, including SHA-256 of those 32 bytes. It then reads the fixed
128-entry × 16-byte program table when present.

The tone table begins at file offset `32 + 128 * 16 = 0x820`.
Each *populated* program (`nTone > 0`) contributes one block of 16 ×
32-byte `VagAtr` tone records. Programs with zero tones do not consume a
block: the `block_index` field is the ordinal of a populated program, not
its raw program number. This matters for banks with sparse program numbering.

Only when **all** packed tone blocks are present does the inspector set
`tone_table_complete: true`. It then reports *active* tones (up to
`nTone` per program): key limits, centre, fine tune, mode, volume/pan,
ADSR words, and the one-based VAG index. It rejects reversed/out-of-MIDI
key ranges, a tone pointing to a different parent program, and VAG indices
outside `1..vags`. A complete tone table gets `tone_table_sha256` as an
audit fingerprint.

When the program table or tone table is incomplete, those fields are marked
incomplete rather than claiming the bank has been validated.

## VAG sizes and optional VB boundary check

A complete tone table allows locating the next **512 bytes**: 256 little-endian
16-bit VAG-size entries. Entries are in **8-byte units**, not bytes. Index 0
also contributes to the running offset; the playable entries are indices
`1..vags`. The inspector reports each playable VAG's offset within VB,
unit count, and byte count, plus `vag_size_table_sha256`,
`vag_zero_entry_bytes`, and `required_vb_bytes`. This last number includes
entry 0 and is *not* the amount of data transferred by the game's CD loader.

A valid complete table sets `vag_size_table_complete: true`. Nonzero sizes
must be multiples of a 16-byte SPU-ADPCM block. Active tones referencing a
zero-length VAG are rejected. An incomplete size table instead returns
`vag_size_table_complete: false` without pretending to check VB.

The optional `--vb` argument checks only whether the **supplied** local VB
has at least `required_vb_bytes`; extra trailing bytes, such as CD-sector
padding, are allowed and reported. If the VH is incomplete or the VB is too
short, verification fails. No VB bytes are extracted or decoded. These
size-based checks do not prove that the supplied VB belongs to the VH; the
original game may transfer data from an offset or in chunks that a standalone
ISO-file analysis does not reproduce. Validate against the runtime loader
before calling any sample mapping faithful.

## Limitations

- The inspector requires a standalone VH containing the standard `pBAV`
  header, not an arbitrary raw VB body or a memory-modified VAB.
- No original game BIN, VH, VB, soundbank, or decoded audio is required for
  automated tests or written to the repository.
- Format/size consistency is not proof of correct sound, sample looping, pitch,
  instrument mapping at runtime, or Switch output.
- For the eventual full audio validation, compare a user-owned local VAB
  against actual `SsVabOpenHeadSticky`/SEQ runtime behaviour and independently
  rendered sound, with copyright assets remaining local.

Format references: Sony PsyQ `libsnd.h` structures (`VabHdr`, `ProgAtr`,
`VagAtr`) and the VandalHearts-PcPort audio subsystem description:

- https://github.com/sega-dreamcast/ball-breakers-moho/blob/master/libsnd.h
- https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/pc-port/subsystems/spu.md


## Experimental raw SPU-ADPCM decoder

The first host-only SPU sample decoder is `tools/decode_spu_adpcm.py`.
It expects **raw 16-byte ADPCM blocks** only. It does not parse a standalone
`VAGp` header or extract samples automatically from a VB bank.

```sh
python3 tools/decode_spu_adpcm.py /local/path/sample.raw /local/path/sample.wav --sample-rate 22050
python3 tests/test_decode_spu_adpcm.py
```

The 22050 Hz command above is an **explicit example rate**, not an inferred
property of raw PS1 sample bytes or proof of Vandal Hearts playback pitch.
A raw sample does not encode the playback sample clock; actual SPU pitch is
set by the instrument and sequence playback engine.

The decoder implements five PS1 SPU two-tap predictive filters, low-nibble
then high-nibble order, arithmetic signed reconstruction, history carried
between blocks, and clipped signed 16-bit PCM output. It rejects truncated
blocks, invalid filter values and shifts above 12, or undocumented upper
loop-flag bits rather than silently changing malformed bytes.

A loop-start flag (0x04) marks the beginning of a repeating region. An
end+repeat flag (0x03) marks the loop end; when no start marker was given
the reference port uses frame 0. Loop metadata is printed but **WAV playback
does not automatically repeat the loop**. As with the PC-port DecodeVag(),
all supplied blocks are decoded even if an end flag appears before the last
block; the earliest such end is reported for diagnosis.

Synthetic regression tests exercise all predictors, clipping, history across
multiple blocks, flag combinations, malformed headers and exact WAV framing.
An independently written scalar oracle checks PCM arithmetic, but no
separate executable reference decoder or original PS1 hardware recording
has been compared yet. This is not evidence that musical notes, pitch,
loop scheduling, ADSR envelopes, or Nintendo Switch audio output are faithful.

Source implementation used to cross-check the algorithm:
https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/platform/pc/src/libsnd.c
