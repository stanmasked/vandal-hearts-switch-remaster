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


## Decode one VAG directly from local VH/VB

The integration utility `tools/decode_vab_sample.py` reuses the full
VH structure inspector, optional VB length verifier, and strict SPU-ADPCM
decoder. It does **not** require a manually extracted intermediate ADPCM
file:

```sh
python3 tools/decode_vab_sample.py \
  /local/path/music.vh /local/path/music.vb \
  /local/path/diagnostic-vag1.wav --vag 1 --sample-rate 22050
```

The `--vag` selector is one-based, consistent with VAB tone references.
The tool calculates the size-table-based offset (including entry zero),
checks the full VH tables and supplied VB bounds, reads only the selected
sample bytes, and produces mono 16-bit WAV. The resulting JSON output
includes VH/tone/size-table fingerprints, selected compressed-sample SHA-256,
PCM SHA-256, VAG offset and size, referenced programs/tones, and loop markers.

**Important:** 22050 Hz is an example *diagnostic* rate, not the original
Vandal Hearts instrument pitch. Raw ADPCM does not encode the SEQ/SPU pitch
registers; the correct playback rate, ADSR, key regions, looping, mixing,
and reverb require subsequent runtime integration. This tool decodes each
provided ADPCM block once, even if the first end flag occurs early.

A new WAV output path is required; existing files and source aliases are
rejected, and no original VH/VB or copyright asset is uploaded or committed.
Validation is based on a consistent on-disk VH/VB pair, not proof that two
independently supplied files belong together. Do not publish the generated WAV.

```sh
python3 tests/test_decode_vab_sample.py
```

The synthetic integration fixture includes a nonzero VAG-zero prefix,
two populated programs with a gap, two independently selected VAGs,
explicit PCM expectations, a looping sample, invalid selector/rate,
damaged headers, truncated sources, and refusal to overwrite existing
outputs. Passing this test is not a hardware or game-music fidelity claim.


## SEQ note to VAB tone lookup (diagnostic)

The read-only helper `tools/resolve_vab_note.py` resolves an incoming
0-based MIDI/SEQ program number and note number against **active** tone
records of a standalone local VH. A matching VB can be supplied for
size-bound checking, but no audio sample is decoded or written:

```sh
python3 tools/resolve_vab_note.py \
  /local/path/music.vh --vb /local/path/music.vb --program 7 --note 60
python3 tests/test_resolve_vab_note.py
```

The lookup models the **selection order** of
`SeqPickTone()` in VandalHearts-PcPort's `platform/pc/src/libsnd.c`:

1. First tone with an inclusive key-range match in the requested program.
2. If none, first key-range match across all populated programs, in
   increasing program/tone order.
3. Otherwise, the tone whose **minimum key** is closest to the note,
   not the tone whose range endpoint is closest. Equal distances retain
   the first candidate.

An empty bank is rejected, and results retain the original sparse program
number, tone slot, VAG number, VB offsets, raw ADSR parameters and header
fingerprints. Range boundaries are inclusive. This helper intentionally
considers only the `nTone` **active** slots validated by the VH inspector;
the PC-port's fallback source loops through all 16 tone slots. Verify any
nonempty inactive slots on a real bank before claiming an identical lookup
for every possible malformed/unusual VAB.

For comparison with the PC-port's approximate software pitch calculation,
the tool also displays `pitch_ratio_approx` and
`pitch_step_approx = int(ratio * 4096)`, using signed 8-bit centre/shift
values and the formula
`ratio = 2 ** (((note - centre) - shift / 128) / 12)`.
These numbers are **diagnostic**: they do not implement Sony's exact
hardware pitch-table quantization or play the note. Runtime ADSR, key-on,
velocity/gain law, channel/program pan, polyphony, interpolation, reverb,
loops and SEQ timing remain separate work.

The tests include overlapping tone ranges, requested-program preference,
sparse program indices, cross-program fallback, lower-bound-only nearest
selection, tie stability, signed pitch metadata, strict parameter validation,
truncated VH/VB and unchanged source inputs. A passing result demonstrates
synthetic lookup consistency only; no original Vandal Hearts music has been
rendered through this tool.


## SPU ADSR and sample cursor (host-only)

The next isolated component is `tools/simulate_spu_voice.py`, which
models the envelope and the 20.12 fixed-point playback position from the
PC-port `platform/pc/src/pc_spu.c`. It has no audio output; all input
is synthetic metadata. Verify it locally with:

```sh
python3 tests/test_simulate_spu_voice.py
make test
```

`SpuEnvelope(adsr1, adsr2)` reads the two unsigned PsyQ ADSR words
(attack shift/step and mode, decay shift, sustain level, sustain rate/mode,
release rate/mode). One `advance()` call represents one 44100-Hz output
sample tick in the reference software SPU. It maintains the fractional
rate counter, saturates the level to `0..0x7fff`, and transitions through
attack/decay/sustain/release. `key_off()` starts release; `advance()`
returns `False` when the envelope has finished.

`SpuSampleCursor(length, loop_start, loop_end, pitch_step)` tracks a
20.12 fixed-point PCM position. A pitch of `0x1000` advances exactly
one source sample per output sample; smaller steps advance fractionally.
With a valid `[loop_start, loop_end)` range it wraps overshooting phase
back into the loop while preserving the fractional part. Without a
valid loop it deactivates after the source end. The pitch-step range
is clamped to `1..0x4000` as in the reference PC renderer.

Synthetic tests exercise attack/decay/sustain/release transitions,
bit-field parsing, stalled maximum rates, fractional rate counting,
exponential release, sustain fade-out, fixed-point pitch stepping,
loop wraps, end-of-sample deactivation, and malformed parameters.

**Scope warning:** matching the PC-port state machines on synthetic
vectors is not matching the hardware SPU in all edge cases. This module
does *not* interpolate or fetch PCM, allocate voices, apply volumes/pan,
synthesize audio, schedule SEQ events, reproduce reverb, or render a WAV.
Runtime 44100-Hz scheduling, mixing, and real-bank validation remain
separate acceptance gates. No original game data is used.
