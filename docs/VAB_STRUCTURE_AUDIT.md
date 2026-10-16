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


## Dry single-note render to WAV

The host-only tool `tools/render_vab_note.py` provides the first **audible
diagnostic note** from a user-owned local VH/VB pair. It integrates
`resolve_vab_note.py`, SPU-ADPCM decoding, the 20.12 fixed-point sample
cursor, and per-output-frame ADSR. It writes a new, non-overwriting
**44,100-Hz mono 16-bit WAV**:

```sh
python3 tools/render_vab_note.py \
  /local/path/music.vh /local/path/music.vb /local/path/one-note.wav \
  --program 7 --note 60 --hold-frames 22050 --tail-frames 8820
python3 tests/test_render_vab_note.py
```

Both `--hold-frames` and `--tail-frames` are explicit **output samples
at 44,100 Hz**, not MIDI/SEQ ticks. In the example, key-off happens
exactly after 22,050 output samples (0.5 seconds); up to 8,820 further
samples are rendered for release (0.2 seconds). Output has exactly
`hold_frames + tail_frames` samples and is padded with silence if the
one-shot sample or ADSR ends earlier. The combined duration is limited to
20 seconds to prevent accidentally creating unbounded loops. An optional
`--gain` value in `0..1` is a **diagnostic** amplitude factor, not the
original game velocity/channel/program/tone-volume law.

The sample is selected according to the PC-port's `SeqPickTone`
priorities and its approximate equal-tempered pitch computation. The
decoder preserves VAG ADPCM loop markers; a repeat loop is actually stepped
during note playback. Each output frame reads the current PCM sample,
advances ADSR and scales that sample, and then advances its pitch cursor.
This reproduces the **ordering** of the corresponding PC-port update
functions. Four-tap integer Gaussian interpolation is now the default;
nearest neighbour is retained as an explicit comparison mode. Pitch is clamped to `1..0x4000` fixed-point units
with `0x1000` at unity speed.

The JSON audit report identifies the selected VAG/program/tone, source
offset/length, input and output hashes, loop markers, frame count,
active-frame count, effective pitch step and final envelope phase.
The tool reads VH and VB without modifying them. It refuses to overwrite
an existing WAV or use the same path as the source data. **Keep generated
WAVs private and local; do not commit copyrighted original audio.**

Synthetic end-to-end tests verify exact PCM output at 44,100 Hz, key-off
timing, ADSR release, fractional pitch stepping, repeat loops, one-shot
silence, invalid ADPCM, truncated VB and output/source overwrite guards.

**Not yet implemented or validated:** original PS1 pitch-register quantization,
velocity and volume law, stereo pan, voice allocation and mixing, reverb,
sequencer timing, Switch audio output, and comparison against real
Vandal Hearts instrument banks. A listening WAV from this utility is
not a game-music or Switch-port acceptance test.


## Integer Gaussian interpolation in the note renderer

The single-note WAV tool now defaults to `--interpolation gaussian` and
uses the 512 PS1 SPU Gaussian coefficients from `tools/spu_gaussian_table.py`.
The four-tap renderer `tools/interpolate_spu_gaussian.py` selects the phase
index `(phase >> 4) & 0xff`, accesses the previous three and current
decoded PCM samples, and applies four **separate** Q15 multiply/right-shift
operations. Adding products before shifting would change the output and
does not follow the reference `pc_spu.c`.

The initial pre-sample history is zero. After a loop wraps, history reads
from the last three samples of the looping section rather than from
the pre-loop attack region. Loop history is checked with synthetic exact
integer golden vectors, including fractional pitch positions. The
output is clipped to signed 16-bit PCM before ADSR scaling.

```sh
python3 tools/render_vab_note.py \
  /local/path/music.vh /local/path/music.vb /local/path/gaussian-note.wav \
  --program 7 --note 60 --hold-frames 22050 --tail-frames 8820
python3 tests/test_spu_gaussian_interpolation.py
```

Use `--interpolation nearest` for older baseline comparisons or to
diagnose differences in pitch stepping separately from interpolation.
It remains available but is no longer the default.

**Verification scope:** these tests validate the integer coefficient
and loop-history path against known vectors from the PC-port implementation.
No multi-voice mixing, original PS1 pitch-table rounding, stereo pan/gain,
reverb, exact Sony hardware timing, or real-game source-bank playback has
been validated. A WAV from this host diagnostic is not a Switch build.


## Dry multivoice stereo rendering

`tools/mix_spu_stereo.py` models the PC port's `SeqNoteOn` velocity
and level path: four **successive integer /127 truncations** (velocity
times channel volume, bank master volume, program volume and tone volume),
then tone/program/channel pan factors, left/right SEQ volume, and finally
the PsyQ **square law applied to each channel separately**. The same
PC-port diagnostic SEQ trim of `1.012` is applied after the square law.
This is not a calibration of real PS1 hardware.

The dry mixer runs at 44,100 Hz with per-voice Gaussian sample fetch,
ADSR advancement, individual pitch cursors and independent L/R gains.
It sums all active voice contributions in floating point, truncates each
channel once, and clips the mixed output to signed 16-bit PCM.
Manual chords still accept at most **32 total notes**. SEQ schedules
use a separate **20-slot** timeline renderer that can reuse those
slots across up to 2048 note-on events during the 20-second host
diagnostic window. This follows the PC port's division between the
20 SEQ slots (0–19) and SFX slots (20–23); it does not imply
32 simultaneously available music voices.

`tools/render_vab_chord.py` turns a user-authored **JSON test schedule**
into a 16-bit **stereo** WAV from matching, locally owned VH and VB files:

```json
{
  "voices": [
    {
      "program": 7,
      "note": 60,
      "velocity": 110,
      "channel_volume": 127,
      "channel_pan": 24,
      "start_frame": 0,
      "hold_frames": 22050,
      "tail_frames": 8820
    },
    {
      "program": 7,
      "note": 64,
      "velocity": 100,
      "channel_pan": 102,
      "start_frame": 4410,
      "hold_frames": 17640,
      "tail_frames": 8820
    }
  ]
}
```

```sh
python3 tools/render_vab_chord.py \
  /local/path/music.vh /local/path/music.vb \
  /local/path/voices.json /local/path/dry-chord.wav
python3 tests/test_mix_spu_stereo.py
```

All timeline numbers are **44,100-Hz output frames**, not SEQ ticks.
Velocity/channel volume defaults to 127, channel pan to 64 (centre),
start frame to 0 and release tail to 0 if omitted. The default
interpolation is integer Gaussian; `--interpolation nearest` allows
baseline comparison. A manual chord supports 1–32 notes. A timeline
from SEQ may hold 1–2048 notes with explicit `voice_slot` indices
0–19; concurrent overlap in one slot is rejected. JSON input is
limited to 64 KiB and the output to 20 seconds. Destination files
must be new: VH, VB, the schedule file and existing outputs are
never overwritten.

The tests verify hard left/right pan, pan-before-squaring,
integer-level stage truncation, polyphonic sum-and-clip,
exact synthetic stereo PCM, delayed note starts, validation, and
source-file immutability.

This tool remains a **dry diagnostic**, not a soundtrack renderer.
SEQ-to-JSON conversion now models 20 reusable music slots, while
real-time note scheduling, exact ADSR liveness, reverb, hardware pitch
quantization and Switch playback remain unimplemented.
Original game audio remains local and must not be committed.

## Host audio CI

`.github/workflows/host-audio-tests.yml` runs a dedicated Python syntax
check and the focused VAB/SPU audio test suite on pull requests,
including the stereo tests. The separate texture-sampling CI is
**not** an audio acceptance test. The full `make test` target also
includes unrelated Map02 tests and was observed failing on a
`test_capture_map02_runtime` binary provenance marker validation;
that unrelated regression needs its own investigation before claiming
the repository-wide suite is green.


## PlayStation SEQ parser and first direct SEQ-to-stereo diagnostic

The host-only `tools/inspect_ps1_seq.py` parses a local PlayStation
`pQES` sequence (maximum 256 KiB), **not a Standard MIDI File**.
The header occupies 15 bytes: 4-byte `pQES` signature, 4-byte version,
big-endian 16-bit PPQN, 3-byte big-endian initial tempo in
microseconds per quarter note, and 2 rhythm bytes. It reads one sequence
of delta-timed MIDI-like channel events, preserving channel running
status. The PS1 tempo event has raw bytes `FF 51 tt tt tt` with
**no SMF-style length byte**; `FF 2F` ends the track.

Parsing is strictly bounded by the local file size. It rejects
truncated/overlong four-byte VLQs, malformed channel payloads, missing
end-of-track and unsupported meta/system events. Audio-frame positions
at 44,100 Hz use exact rational tempo integration across delta times,
then floor at each event, so repeated rounding does not accumulate.
Results include each event's absolute tick and frame, SEQ SHA-256,
bytes consumed and trailing-padding count. Default PPQN/tempo of 480
and 500000 are used only if those header fields are zero.

```sh
python3 tools/inspect_ps1_seq.py /local/path/music.seq
python3 tests/test_inspect_ps1_seq.py
```

The second utility, `tools/seq_to_chord_schedule.py`, creates the
same JSON `{"voices": [...]}` format accepted by our existing
`tools/render_vab_chord.py`. At each note-on, it snapshots channel
program, CC07/CC0B volume, CC0A pan, note and velocity. Note-off,
velocity-zero note-on, retrigger, CC78/CC7B all-notes-off and end-of-track
close the note. The note's timeline is in **44,100-Hz audio frames**, not
MIDI ticks. Same-frame note-on/off is quantized to a one-frame hold.
A diagnostic release tail defaults to 4410 frames (0.1 seconds).

```sh
python3 tools/seq_to_chord_schedule.py \
  /local/path/music.seq /local/path/voices.json --release-frames 4410
python3 tools/render_vab_chord.py \
  /local/path/music.vh /local/path/music.vb \
  /local/path/voices.json /local/path/dry-seq.wav
```

The convenience utility `tools/render_ps1_seq.py` combines the
above steps **without writing intermediate JSON**:

```sh
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/diagnostic-seq.wav --release-frames 4410
python3 tests/test_seq_to_chord_schedule.py
python3 tests/test_render_ps1_seq.py
```

Keep all original SEQ/VH/VB assets and generated WAVs local. These tools
never overwrite any input or existing output, and no copyrighted assets
are committed. The test suite uses only small fabricated SEQ/VAB/VAG
fixtures and checks the full read-only path to stereo WAV.

**Acceptance boundaries:** this remains an **offline diagnostic**,
not a music player. The source PC port allocates 20 music voices
and reserves other slots for SFX. The converter now uses a 20-slot
allocator: lowest free slot first, then round-robin stealing only
when every music slot is busy. On stealing, the former note is
truncated and its ownership is cleared, so a later stale Note Off
cannot stop the new owner.

**Approximation:** an ADSR release voice is considered busy for the
specified diagnostic `release_frames`, not its true live SPU envelope
lifetime. Same-frame notes stolen before producing a sample are
omitted. This permits up to 2048 note-on events across 20 seconds,
but does not implement true SPU voice occupancy, infinite or finite
sequence repeats, sustain pedal simulation, live controller changes,
pitch bend, block-accurate PC-port scheduler advancement, reverb or
exact PlayStation pitch rounding. Sequencer audio is not wired into
the Nintendo Switch NRO. Real-bank listening comparison and an
actual Switch run are still required for music-port acceptance.

## Voice-slot regression coverage

`tests/test_seq_voice_slots.py` validates the 20-slot allocator against
synthetic streams with 45 serial note-ons, a 22-note overflow causing
round-robin steals of slots 0 and 1, a later stale note-off, and
same-frame steals. The streaming mixer verifies that two simple
non-overlapping voices produce byte-for-byte the same PCM as the
earlier static mixer. Overlapping schedule intervals for a single
slot are rejected.

The dedicated `Host SPU audio regressions` workflow runs these tests,
rather than relying on the unrelated texture-only workflow. A passing
host regression is evidence of synthetic behavior only.


## Bounded Sony SEQ track repeats (offline)

`tools/repeat_ps1_seq.py` implements the PC-port `SsSeqPlay`
`repeatCount` convention at the **event level**:

- `--repeat-count 1`: play once, the default.
- `--repeat-count 2..64`: play the track that many times.
- `--repeat-count 0`: repeat indefinitely, **only** when
  `--max-frames` explicitly sets a finite stopping window at 44100 Hz.

```sh
# Inspect three play-throughs without creating audio:
python3 tools/repeat_ps1_seq.py /local/path/music.seq --repeat-count 3

# Inspect a bounded 'infinite' loop, stopping at 10 seconds:
python3 tools/repeat_ps1_seq.py /local/path/music.seq \
  --repeat-count 0 --max-frames 441000

# Direct local VH/VB dry stereo rendering, no intermediate JSON:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/repeated-note.wav --repeat-count 2

# One bounded 'infinite' 10-second diagnostic render:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/bounded-loop.wav --repeat-count 0 --max-frames 441000
python3 tests/test_repeat_ps1_seq.py
```

For clean `FF 2F` seams before the last iteration, the event stream
uses `loop_boundary` instead of `end_of_track`. Like the reference
PC port, this **does not issue note-offs to held voices** and it
preserves controller/program state and the current tempo. It resets
the implicit MIDI running status by parsing the original event stream
on each iteration. Each tick delta is converted to a 44100-Hz frame
using exact rational arithmetic, *including inherited tempo at the
start of later cycles*. This avoids restarting every cycle at the
header tempo when a prior cycle ended with a tempo change.

The final finite loop terminates at `end_of_track` and releases
held notes. In infinite mode the specified `--max-frames` hard
stop produces a marked end event (`truncated_by_window`) and
truncates any pending release tail rather than writing past the
requested window. A zero-tick sequence is rejected for infinite
replay; count, event and 20-second output limits prevent runaway work.

This is **not exact original playback timing**: the PC-port advances
musical ticks in audio-buffer blocks via `PC_SeqAdvanceSamples`.
Its end-of-track handler resets accumulated tick budget; our offline
tool models ideal continuous tempo integration across loop seams.
Real-world song repetition, note scheduling, voice lifetime, pitch,
reverb and Switch output still need comparison to the actual game
runtime and a hardware/PC recording.

No original SEQ/VH/VB files or generated game audio are committed.
Only synthetic tests and parser/rendering code are included.


## SPU ADSR-driven SEQ voice lifetime (opt-in)

The host-only `tools/spu_voice_lifetime.py` now implements an ADSR/PCM
liveness clock for the **20 SEQ voice slots**. Its per-frame operations
reuse exactly the same `SpuEnvelope` and `SpuSampleCursor` classes as
the diagnostic stereo renderer. This means slot occupancy ends when
either the envelope reaches `off` or a nonlooping decoded sample
reaches its end, rather than when a fixed synthetic release timeout
expires. A voice in release still occupies its slot until it actually
becomes inactive. The caller reads the selected tone's **ADSR1/ADSR2**,
PCM sample count, loop markers and pitch from a validated local VH/VB
pair (nothing is extracted to an intermediate file).

To compare old and new voice allocation without losing a reproducible
baseline, the **direct** offline SEQ renderer exposes an explicit
mode switch:

```sh
# Historical fixed tail, remains the default:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/fixed.wav --voice-lifetime fixed --release-frames 4410

# Sample-accurate synthetic SPU-envelope/cursor liveness:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/adsr.wav --voice-lifetime adsr

python3 tests/test_spu_voice_lifetime.py
```

The `--voice-lifetime adsr` mode is *opt-in*. The standalone
`seq_to_chord_schedule.py` JSON converter continues to use fixed
`--release-frames` unless programmatically given VAB-backed
`voice_spec_for_note` metadata. New regression tests cover natural
one-shot exhaustion, sustain-level auto-fade, two-frame rapid release,
20-slot free/reuse and round-robin behavior, stale note-off ownership,
and byte-level integration from synthetic local SEQ/VH/VB to stereo WAV.

The clock stops at the first inactive output frame. For SPU ADSR
completion, that frame emits no PCM; for one-shot sample-cursor
exhaustion, the final cursor-advance frame has already been rendered.
When release does not finish before the 20-second safety boundary,
the offline timeline is clipped and a `lifetime_capped` diagnostic
marker is reported. This is a **bounded diagnostic**, not a substitute
for the live PC-port audio service.

**Remaining fidelity caveats:** the source port's SEQ advances in
512-frame audio blocks, and its voice allocator synchronizes with
`PC_SpuVoiceActive` between blocks; offline event timestamps follow
the ideal rational frame timeline. Audio-block event boundaries,
voice liveness when OpenAL buffers underrun, real hardware SPU timing,
per-voice reverb, and actual Nintendo Switch output have not been
validated. This model must not be called PS1-perfect or Switch-ready
solely because host synthetic CI passes.


## PC-port 512-frame SEQ scheduling (opt-in host diagnostic)

`tools/schedule_ps1_seq_blocks.py` models the timing order in the
source PC port's `pc_spu.c` and `libsnd.c`:

1. At the start of every **512-frame** output buffer,
   `PC_SpuService()` calls `PC_SeqAdvanceSamples(512)`.
2. `SeqAdvanceByUsec()` adds one whole buffer's worth of musical
   ticks to its pending tick budget, using the tempo **at the start
   of the buffer**.
3. All events whose deltas are now due are dispatched **before**
   `SpuRenderBlock()` renders those 512 PCM frames. In the diagnostic
   schedule these events therefore share that block's starting frame.
4. A tempo event changes the rate of **subsequent** buffers. It does
   not retroactively modify the current buffer's already calculated
   tick increment.
5. A clean SEQ repeat resets the remaining tick budget to zero,
   but preserves the tempo, instrument/channel state and held notes.
   Running status starts fresh with the next pass.

For comparison the existing `ideal` mode remains the default.
The new `pc_block512` mode is selected explicitly:

```sh
# Inspect SEQ dispatch frames without generating audio:
python3 tools/schedule_ps1_seq_blocks.py \
  /local/path/music.seq --repeat-count 2

# Render a user-owned, locally stored SEQ + VH/VB with block scheduling:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/block-diagnostic.wav \
  --timing-mode pc_block512 --voice-lifetime adsr

# Contrast with continuous rational tick integration:
python3 tools/render_ps1_seq.py \
  /local/path/music.seq /local/path/music.vh /local/path/music.vb \
  /local/path/ideal-diagnostic.wav --timing-mode ideal

python3 tests/test_schedule_ps1_seq_blocks.py
```

The block model uses exact rational arithmetic to make repeatable
synthetic regression tests; the source PC code uses double-precision
tick budgets. It reproduces the order of event dispatch versus PCM
rendering, **not** the real OpenAL queue fill, buffering latency,
under-runs, audio clock recovery, the extra stuck-note reaper,
Sony's original hardware timings or real Nintendo Switch playback.
It is deliberately a separate mode so comparisons can reveal any
audible differences from the previous idealized timeline.

Host tests cover first-block events, discrete 512-frame boundaries,
a tempo change in the middle of a single tick-budget drain, repeated
tracks resetting budget, bounded infinite repeats, validation, local
file immutability and the complete synthetic SEQ/VH/VB-to-WAV pipeline.

All inputs and generated game audio must remain local; no proprietary
music assets are included or uploaded.


## Native Switch PCM transport foundation (C, asset-free)

`source/vh_audio_stream.h` and `source/vh_audio_stream.c` introduce a
portable C11 audio FIFO for the eventual native SEQ/SPU producer. It
transports **interleaved signed 16-bit stereo PCM at 44,100 Hz**.
The ring holds 4096 stereo frames (~93 ms), and uses 512-frame producer
blocks to match the reference PC-port software SPU's render granularity.

The FIFO has no heap allocation, SDL dependency, file access or
decoding in its reader. Underruns are explicitly zero-filled, overruns
never overwrite unread audio, and both are counted separately. A
callback that reads more than was queued receives all requested frames,
with the missing tail filled with silence. Source files stay untouched.

`probes/sdl2_audio_smoke.c` now uses the FIFO in the Switch SDL2
audio callback. Its main thread generates a **synthetic** 441 Hz stereo
square wave (different left/right levels) in 512-frame blocks and
buffers approximately 2048 frames. `SDL_LockAudioDevice()` protects
main-thread producer access; the callback reads without locking,
allocating, decoding or waiting on the sequencer. The SDL device
is opened with `AUDIO_S16SYS`, 44,100 Hz, two channels and requested
512-frame callbacks without permitting format/rate substitution.

This is a **transport feasibility probe**, not Vandal Hearts music
playback: the native C engine does not yet parse SEQ, decode VAG,
synthesize 20 musical voices, or connect to the game's NRO. An
observed callback means the SDL callback ran; it does **not** prove
that the Switch speaker/headphone path emitted audible sound.

Build and test locally:

```sh
# Pure C11 host tests: no SDL, game assets or Switch required.
make test-audio-stream

# With installed devkitPro Switch SDL2 portlibs:
make sdl2-audio-probe

# A generated NRO can be sanity-checked for its binary container:
python3 tests/check_nro.py build/sdl2-audio-switch-probe.nro
```

`tests/test_vh_audio_stream.c` checks frame order, stereo interleave,
FIFO wraparound, full-ring overflow, silence on underrun, reset,
NULL-input safety and 6000 deterministic randomized enqueue/dequeue
operations. `.github/workflows/host-audio-tests.yml` compiles/runs
the host regression with warnings-as-errors and again under UBSan.
`.github/workflows/switch-native-pcm.yml` separately cross-compiles
the C transport with devkitPro's AArch64 compiler. Cross-compilation
alone is **not** evidence of a successfully linked NRO or on-device
audio output.

**Still pending:** one integrated native PCM producer sourcing the
actual SEQ/VAB/SPU work rather than a synthetic tone, Switch NRO linking
and runtime confirmation, sound quality against the original,
threaded mixer backpressure/latency profiling and hardware testing.
Original game resources and generated game audio remain local.


## Native SPU-ADPCM decode and first C11 music-voice producer

The original Python host decoder remains the reference for byte-level
synthetic validation. The new portable native modules are:

- `source/vh_spu_adpcm.h/.c`: headerless 16-byte PS1 SPU-ADPCM
  decoder producing 28 mono PCM16 frames per block. It handles the
  five predictor filters, arithmetic-right-shift rounding for
  negative samples, clipping **before** predictor-history updates,
  first end-block and end+repeat/loop-start flags. Invalid predictor,
  shift, flag bits, length or output capacity are rejected before PCM
  decoding. Caller owns all memory; **no VAB or original game assets
  are embedded**.
- `source/vh_native_spu.h/.c`: 20 music-voice slots with key-on/key-off,
  first-free/round-robin slot allocation, PC-port-style per-output-frame
  ADSR and pitch stepping, repeat-loop handling and dry stereo summing.
  Each voice borrows a caller-owned decoded PCM array for its lifetime.
  **Nearest-sample interpolation** is used for this initial native
  version; the earlier Python-only four-tap Gaussian model is not yet
  implemented in C.
- The `vh_native_spu_pump()` helper generates at most **512 stereo
  frames** only if the ring has sufficient space; a full FIFO returns
  zero **without consuming synthesis time**. Producer and callback
  access still requires synchronization.
- `probes/sdl2_audio_smoke.c`: exercises the complete native path
  with a **fabricated 32-byte looping ADPCM sample**. It decodes that
  sample, keys on one SPU voice, renders 512-frame stereo chunks in
  the main loop, queues them into `vh_audio_stream.c`, and supplies
  SDL2 callback reads. It no longer generates a synthetic square
  wave inside the callback itself. No sequence parser, music bank,
  game audio or external file access is involved.

Synthetic verification:

```sh
make test-audio-stream
python3 tests/test_native_spu_adpcm.py
# On a Switch devkitPro setup with SDL2 portlibs:
make sdl2-audio-probe
```

The C11 host regression `tests/test_vh_native_spu.c` tests the
ADPCM → voice → stereo FIFO integration, exact short ADSR attack and
release vectors, looping, fractional pitch, one-shot termination,
20 voice slots, overflow backpressure and validation. The differential
test `tests/test_native_spu_adpcm.py` builds the identical decoder
source as a host shared object and checks byte-for-byte output and loop
metadata against Python on 110 randomized synthetic ADPCM sequences.
The audio CI also compiles/runs the native SPU test under UBSan.
`.github/workflows/switch-native-pcm.yml` now requests **AArch64
cross-compilation of all three native transport/decoder/synth objects**.

**Not yet in this native implementation:** parsing real VH/VB banks or
SEQ files, native SEQ event dispatch and controller changes, 4-tap
Gaussian interpolation, exact original gain law and stereo pan,
reverb, voice-release comparison on the console, streaming from
actual game resources or validating audible Switch output. Passing
synthetic host CI or compiling individual AArch64 objects is not
proof that the full game music is running on Nintendo Switch.


## Native Gaussian four-tap SPU interpolation (C11)

The native SPU engine now includes `source/vh_spu_gaussian.h/.c`.
This embeds **exactly 512 int16 coefficients** extracted from the
existing Python `tools/spu_gaussian_table.py` reference, without
floating-point approximation or use of copyrighted sample assets.

Each fetch uses the source port's index `gi = (phase >> 4) & 0xff`
and four neighboring samples at positions `index-3`, `index-2`,
`index-1`, `index`. The four coefficient products are each divided
by 32768 **with signed floor rounding**, then added and clipped to
signed 16-bit PCM. This is important: summing before the shift or
using C's default signed integer division changes the low PCM bits.

Playback before the start of the sample uses zero-filled history.
When a looping VAG first wraps, the `looped` flag switches earlier
tap positions to the end of the repeat interval, matching the Python
host reference. The same flag is reset by a new key-on.

`vh_native_spu_set_interpolation(spu, VH_SPU_GAUSSIAN)` enables
Gaussian in an initialized SPU state. `VH_SPU_NEAREST` remains the
zero-initialized default for legacy exact-output comparisons.
The **SDL2 Switch audio probe now explicitly selects Gaussian**
for its fabricated looping SPU-ADPCM sample.

Host validation:

```sh
make test-audio-stream
python3 tests/test_native_spu_gaussian.py
```

`tests/test_vh_native_spu.c` checks exact native PCM against
hard-coded four-tap Gaussian output frames around the first
loop wrap and subsequent iterations. The Python differential
test compiles the same native `vh_spu_gaussian.c` C11 source into a
temporary host library and compares individual integer samples to
`gaussian_voice_sample()` across a deterministic corpus of signed
PCM values, fractional phases, startup histories and loop positions.
The `Host SPU audio regressions` workflow runs these and native
UBSan checks. `Switch native PCM transport cross-compile`
includes an AArch64 object for the new Gaussian module.

**Current limits:** although Gaussian coefficients and arithmetic
follow the software PC reference, the native engine still lacks
native PS1 SEQ/VAB parsing and timing, original full controller
and velocity-dependent gain/pan law, reverb, runtime voice ownership,
and hardware-based auditory acceptance. The synthetic SDL2 probe is
not playback of original Vandal Hearts music. Cross-compiling
C objects is not a confirmed NRO playback test.


## Native pQES SEQ scheduler and 512-frame Switch audio probe

The first C11 implementation of Sony's single-track **pQES SEQ**
scheduler has been added as `source/vh_native_seq.h/.c`.
This is a native event reader and 512-output-frame clock that drives
the existing `VhNativeSpu` interface. It is **not** a Standard MIDI
File player or a new interpretation of raw VAB bank samples.

For now it uses an explicit `VhSeqResolve` callback supplied by
the caller to map `(program, note, velocity, channel volume, pan)`
to caller-owned decoded PCM, ADSR, pitch, looping and stereo gains.
The callback interface intentionally separates the SEQ scheduler from
the future native VH/VB bank importer. No proprietary asset bytes are
embedded or committed.

**Supported SEQ events:** Note On, Note Off (including velocity-zero
Note On), CC07/CC0B volume, CC0A pan, CC78/CC7B all-sounds-off,
Program Change, ignored polyphonic/channel pressure and pitch bend
(the latter is not yet applied), PS1 meta `FF 51 tt tt tt` tempo
**without MIDI meta-length**, and `FF 2F` end-of-track. Running
status and 1–4-byte variable-length deltas are parsed with hard
bounds; event data must use MIDI seven-bit values. Unexpected status,
truncated events, unrecognized meta events, missing end-of-track,
oversized files (over 256 KiB) or zero-duration infinite loops
cause initialization to fail before the source bytes or SPU state
are changed.

**Timing:** `vh_native_seq_advance_block()` adds one 512-frame
tick budget using tempo at the start of the audio block and processes
all events whose deltas fit that budget before the associated PCM
render, matching the software PC port's service ordering. A tempo
event changes later audio blocks. A clean `FF 2F` loop seam
clears the remaining tick budget and resets running status while
keeping channel settings and held note ownership. Finite playback
supports 1–64 repeats; repeat count 0 means infinite until a
caller-initiated stop. Every block limits the number of processed
events to 20,000, preventing unbounded zero-delta event dispatch.

**Voice ownership:** first-free allocation and round-robin stealing
are delegated to the same 20-slot `VhNativeSpu`. On replacement,
the prior note's channel back-reference is cleared. Thus a delayed
Note Off cannot release a new occupant of its old slot. After
Note Off, the SPU voice may continue its ADSR release and will be
reused only when the SPU marks it inactive or all voices are occupied.

**SDL2 probe:** the Switch probe uses a fabricated `pQES` sequence
(program 7, CC07/CC0A, repeated 240-tick note-on/off) and a
fabricated looping PS1 ADPCM sample. The native resolver maps its
single synthetic instrument to already decoded PCM and dry gains.
The main thread invokes SEQ advance **before** `vh_native_spu_render`
for each 512-frame chunk, then writes into the synchronized SDL2
FIFO. The audio callback only reads PCM, zero-filling underruns.
This is a *synthetic native event-to-audio integration test*, not a
real soundtrack or evidence of audible console output.

Host tests:
```sh
make test-audio-stream
# Test native 512-frame event dispatch and stateful voice allocation:
./build/test_vh_native_seq
# devkitPro + Switch SDL2 portlibs required for an NRO:
make sdl2-audio-probe
```

`tests/test_vh_native_seq.c` covers malformed sequences and input
immutability, SEQ header values, Note On/Off, controller/program
snapshots, MIDI running status, tempo events, finite loop seams,
20-slot stealing with stale note-off, 512-frame ring backpressure
(no clock or SPU advancement when full), and synthetic PCM output.
Both optimized strict C11 builds and UBSan are specified in the
`Host SPU audio regressions` CI workflow. The AArch64 cross-compile
workflow now includes `vh_native_seq.c`.

**Limitations:** a real native VAB tone/sample resolver has not yet
been implemented. The synthetic resolver does not implement the
full original PsyQ gain law. There is no native game SEQ data
acquisition, live multi-track playback, pitch bend, reverb, exact
OpenAL latency simulation or real Nintendo Switch listening test.
Compilation or CI acceptance alone would not establish a working
game-music port.
