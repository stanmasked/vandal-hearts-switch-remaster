# M_MAP02.PRS vs M_MAP02.DAT — evidence reconciliation (2026-10-15)

This note reconciles the older "missing GFX 241/243" hypothesis with the user's existing source-disc audit `vh_map02_resource_audit_2026-10-15.md`. It does not include or redistribute game data. Values below were reported by that prior audit; they have not been independently re-extracted in this repository.

## Verified in the prior local-disc audit

- Mode 2 image data was read in 2352-byte sectors with 2048-byte payloads at +24.
- `DATA/M_MAP02.PRS` SHA-256: `c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387`.
- Decompression yielded 187264 bytes (616 × 304 bytes), SHA-256 `dd98f466fbf4f1019cf04d9b19dd85861afa61e97d0470ce796a4cb83b989382`.
- Relative to the first 187264 bytes of `DATA/M_MAP02.DAT`, there were exactly **two** differing bytes:

| Byte offset | Record | Face | PRS local GFX | DAT local GFX |
| ---: | ---: | ---: | ---: | ---: |
| 74048 | 243 | 0 | 241 | 98 |
| 97152 | 319 | 0 | 243 | 150 |

- The inspected desktop port load path selects `CDF_M_MAP02_PRS` for `gState.mapNum == 11`; `LoadMap` adds 400 to nonzero local GFX IDs and texture loading selects LAND_DT **record 11**. The resource basename `M_MAP02` is **not** evidence for zero-based LAND_DT block 2.
- The previously examined atlas patches all contained meaningful image data: local GFX 98→498 (CLUT 35, UVWH 64,96,15,15), 241→641 (CLUT 35, 240,192,15,15), 150→550 (CLUT 33, 224,128,15,15), 243→643 (CLUT 33, 240,208,15,15).
- CLUT 35 palette entry 0 was `0x9c87`, not transparent black. Palette *index* 0 is not sufficient proof of transparency.
- The audited drawbridge/map handlers did not modify the two target faces, but other runtime changes have not been excluded.

## Consequence

The question is **which original mapping is intended and rendered**, not whether the four patch slots contain texture data. The earlier `docs/MAP02_TEXTURE_AUDIT.md` zero-byte notes, and especially `tools/check_map02_raw.py` which assumes zero-based LAND_DT block 2, **must not be used to conclude that the game has missing textures** for resource `M_MAP02`.

Neither replacing PRS references with DAT references nor assigning synthetic UVs is justified at present.

## Reproducible provenance check

The read-only `tools/compare_map02_variants.py` accepts a **decompressed** `M_MAP02.PRS` stream and corresponding `M_MAP02.DAT`. The `matches_prior_disc_audit` field checks only the two recorded byte differences: synthetic inputs can satisfy this signature. Use `--require-prior-provenance` to also require the archived decompressed PRS SHA-256 fingerprint. This still does not prove which variant the renderer actually selects. No game assets are committed.

## Classifying post-LoadMap face observations

The read-only comparison tool accepts `--runtime-capture /local/path/capture.json` alongside decompressed PRS and DAT. The JSON file is a list with exactly two entries, each containing integer fields `record_index`, `face`, `local_gfx`, and `runtime_gfx`. For example, a **hypothetical**, not observed, PRS capture:

```json
[
  {"record_index": 243, "face": 0, "local_gfx": 241, "runtime_gfx": 641},
  {"record_index": 319, "face": 0, "local_gfx": 243, "runtime_gfx": 643}
]
```

The tool classifies these observations as PRS, DAT, mixed or neither and checks the expected local-to-global GFX translation (+400 for nonzero indices). **This does not collect runtime observations**; the game must be instrumented separately. Nor does a PRS match alone establish texture visibility, tpage, CLUT, flags or screenshot correctness.

## Next decisive runtime verification

Trace the actual load and drawing of faces `(z=8,x=19,face=0)` and `(z=11,x=11,face=0)`: capture local GFX, global GFX, UV, CLUT, tpage and draw flags after `LoadMap` and on each rendering pass. Compare those records to a gameplay screenshot captured from the original build. Determine whether PRS or DAT data is actually used at runtime before attempting artistic repairs.

Upstream source baseline inspected in prior audit: `HalmyLyseas/VandalHearts-PcPort` at `14552fffa0e0b47e02b57592e274fc6e7a649923`.

This is a provenance and decision document, not a runtime trace or an assertion that the artwork is visually correct.


## Machine-checked source selection (2026-10-16)

The pinned US PC-port source at commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`
has an **explicit** `LoadMap` branch for `gState.mapNum == 11`:

```c
case 11:
   gMapDataSizeX = 28;
   gMapDataSizeZ = 12;
   gMapSizeX = 24;
   gMapSizeZ = 12;
   gMapMinX = 0;
   gMapMinZ = 0;
   gMapMaxX = 23;
   gMapMaxZ = 11;
   LoadCdFile(CDF_M_MAP02_PRS, 1);
   break;
```

This is **positive static evidence that the normal map-11 load path
requests PRS rather than DAT**. The active 24×12 region includes both
disputed target positions, (z=8,x=19) and (z=11,x=11). The loader's
28-column in-memory stride is a different dimension from the 24-column
active playable area.

`tools/audit_map02_load_source.py` independently checks the actual
branch, exact source Git blob ID, map bounds, row-pointer setup,
`ProcessMapFileData` call, global GFX offset, and order of these
operations. It intentionally fails on changed resource selection,
unexpected dimensions or altered source unless `--allow-modified-source`
is requested. The latter marks the report as noncanonical.

To reproduce against a local **unmodified** pinned PC-port checkout,
from the remaster project root:

```sh
python3 -m tools.audit_map02_load_source   /path/to/VandalHearts-PcPort/src/states/game_setup.c   > map02_source_selection.json
```

The upstream checkout is also audited in
`.github/workflows/map02-upstream-trace.yml`. The extended audit
additionally checks two pinned upstream files:

- `include/cd_files.h` assigns `CDF_M_MAP02_PRS = 151`.
- `src/core/cd.c` maps this index in `gCdFiles` to starting sector
  `0x1bcc`, 12 sectors (`0x0c`), and destination
  `gScratch1_801317c0`. `LoadCdFile()` initializes its sector
  and count directly from the table.

Use `--cd-source /path/to/src/core/cd.c --cd-header
/path/to/include/cd_files.h` to include these pinned CD-table checks
in the source audit. The resulting JSON includes the table entry,
sector count and both source fingerprints. No game disc is needed
to establish this source-level linkage. These are numbers from the
**US PC-port's compiled CD file table**, not independent measurements
of a physical game disc.

**Limits:** requesting `CDF_M_MAP02_PRS` in C does not prove which
actual disc bytes were supplied, whether another runtime routine
overwrote the target tile indices, or whether a submitted textured
quad was visible. Source evidence supports PRS as the intended *load
path*, not as the final validated pixels. The two differing DAT records
are retained as comparison evidence and are not rewritten.


## Read-only sector-to-PRS verification (no asset export)

The pinned US CD table maps `CDF_M_MAP02_PRS` to twelve 2048-byte
payload sectors starting at `0x1BCC`. The original
`src/maps/unpack.c` reads the first **four bytes** of the PRS stream
as a little-endian **compressed payload length**, then unpacks the
following bytes into map models. The new tool
`tools/audit_map02_disc_prs.py` reproduces that bounded decompression
algorithm in Python.

It reads **only** the relevant sectors from a legally owned disc image,
supports raw 2352-byte Mode2 Form1 sectors (2048-byte data begins at +24)
or plain 2048-byte ISO sectors, and reports the two face-zero local GFX
and their would-be global (+400) indices. No asset bytes are written or
committed. It requires the full 616×304-byte decompressed map and checks
against the prior archived SHA-256 and PRS GFX values. The archived
compressed SHA-256 is compared against both the header-determined logical
PRS stream and the sector-padded payload, since the archived hash's
padding convention must not be guessed.

From the remaster project root, using an existing extracted PRS file:

```sh
python3 -m tools.audit_map02_disc_prs   --prs-file /your/owned/M_MAP02.PRS --require-prior-provenance
```

Or from a **single-track** raw Mode2 Form1 BIN containing the expected
absolute sector indexing:

```sh
python3 -m tools.audit_map02_disc_prs   --disc-image /your/owned/game.bin --layout mode2-2352   --require-prior-provenance
```

Use `--layout iso-2048` for a file consisting of contiguous 2048-byte
logical sectors. If the BIN starts at another track origin or contains
a different pregap convention, calculate that track's offset from the
actual **CUE layout** and supply it explicitly using
`--sector-bias N`; this tool does *not* guess, parse CUEs, or
automatically try offsets. A failure at the expected sector is not
proof that the game data is incorrect until its image layout is known.
Raw sectors with a mismatched XA subheader, wrong mode, Form2 or
incorrect Mode2 Form1 EDC are rejected. P/Q ECC parity is not validated.

If your local installation also has `M_MAP02.DAT`, add its
path to the same read-only command:

```sh
python3 -m tools.audit_map02_disc_prs \
  --disc-image /your/owned/game.bin --layout mode2-2352 \
  --dat-file /your/owned/M_MAP02.DAT --require-prior-provenance
```

The `dat_comparison` report then independently counts differing bytes
between the decoded 616-tile PRS and the first 187264 bytes of DAT.
It checks that **only** face-zero GFX bytes differ: PRS local 241 vs DAT
98 at record 243, and PRS local 243 vs DAT 150 at record 319.
The strict provenance option requires both this exact two-byte pattern
and the archived decompressed PRS SHA-256. Test fixtures intentionally
reproduce the two-byte pattern but cannot pass the authentic PRS digest.
No PRS or DAT data is exported.

A match with the archived **decompressed PRS SHA-256** and the local
GFX pair 241/243 would support the archived disc-audit result with
independent sector extraction. It would **not** prove that the running
game never modifies tiles, that the hardware draws them, or that the
visible artwork matches the source. The command is read-only and
synthetic end-to-end tests require no copyrighted assets.


## Native upstream decompressor differential test

An additional offline verification step compiles the **actual**
`UnpackMapFileData` function extracted from the pinned
`src/maps/unpack.c` into a temporary host executable with
`PC_PORT` enabled. The tool
`tools/verify_map02_unpack_equivalence.py` compares every byte of
the original C decoder's output with the Python
`tools.audit_map02_disc_prs.unpack_prs` output over a deterministic,
non-copyrighted corpus.

The corpus covers literal tokens, absolute and relative 1 KiB
dictionary references, long literal runs, randomized literal bytes,
**32 seeded mixed-token streams**, an additional 1 KiB dictionary
wraparound stress test, and a complete **187264-byte synthetic map**
whose two target face bytes are 241 and 243. The test deliberately
rejects a fake C decoder that returns no output. The original
upstream Git blob SHA-1 is checked before compilation.

```sh
python3 -m tools.verify_map02_unpack_equivalence   /local/VandalHearts-PcPort/src/maps/unpack.c   > /tmp/map02-prs-decoder-comparison.json
```

The GitHub Actions upstream audit performs the same byte-for-byte
check against the pinned public PC-port checkout. A passing result
validates decoder equivalence **on the test corpus only**; it is
not a measurement of any user's disc, a formal proof for every possible
compressed input, or evidence of displayed pixels. No original
gameplay assets are ever placed in CI.


## One-disc sector integrity and PRS/DAT provenance (2026-10-16)

The read-only `tools/audit_map02_disc_prs.py` audit now includes
**CD-XA Mode2 Form1 EDC verification** for every selected raw 2352-byte
sector. It compares the little-endian 32-bit EDC at raw offset
`0x818` against a CRC calculated across
`[0x10, 0x818)` with polynomial
`0xD8018001`, seed 0, and no final XOR. A corrupt sector aborts the
audit before any decompressed GFX conclusions are reported. The tool
checks EDC, **not** the P/Q ECC parity. Plain 2048-byte ISO images
lack those physical checksums, so only their payloads can be audited.

A single user-owned PS1 BIN/ISO file can supply **both** map variants;
there is no longer any need to export the DAT file manually:

```sh
python3 -m tools.audit_map02_disc_prs   --disc-image /path/to/owned/game.bin   --layout mode2-2352   --dat-from-disc --require-prior-provenance
```

The source selection is still the US pinned `CDF_M_MAP02_PRS`
entry: PRS starts at LBA 7116 (12 sectors). The companion DAT is at
LBA 6999 (117 sectors), nominal logical file length **238336 bytes**.
Each resource is read from its specific sector range, and DAT is trimmed
to the ISO file's documented byte size before hashing. On a raw BIN,
this checks **129 Mode2 Form1 sector EDCs** in total.

`--require-prior-provenance` is intentionally stricter than
comparing just the two GFX numbers: it requires the archived logical
compressed PRS SHA-256
`c370660f7f13e6d6e76f4126a45418bc9c64c747de8309ca946d37b502516387`,
the archived decompressed SHA-256
`dd98f466fbf4f1019cf04d9b19dd85861afa61e97d0470ce796a4cb83b989382`,
and (when DAT is supplied) its archived **238336-byte** SHA-256
`07666bd80b87de763ef7312ecaeaa0bf747ebfe49db032fa68c9af675d151c31`
plus the exact two-byte PRS/DAT signature. Failure means the
input is not proven identical to the archived audit; it is not
automatically proof of tampering because a different game revision
or track-origin offset may be involved. For unusual CUE layouts use
an explicitly calculated `--sector-bias`.

Synthetic tests include corrupted EDC in the PRS and DAT ranges,
single-image extraction for raw Mode2 and 2048-byte ISO, and rejection
of synthetic data that matches GFX values but not archived hashes.
**This new tool has not yet read the actual user's disc image in the
current working environment**; previous original-disc audit reports
remain separate historical evidence.


## Four-swatch source pixel proof (2026-10-16)

The utility `tools/map02_texture_pixel_proof.py` is a **local-only, read-only**
source-pixel comparison for the two disputed map faces. It reads from
the user's own Mode2/2352 BIN or 2048-byte-per-sector ISO:

- `M_MAP02.PRS` at LBA 7116 and `M_MAP02.DAT` at LBA 6999
- `F_TEX01.DAT` at LBA 4374 (32768 bytes, 16 sectors)
- `LAND_DT.DAT` at LBA 4954 (123993 bytes, 61 sectors), **block 11**

The PRS model is unpacked and the two target face-0 GFX values are
validated before any sample is taken. The utility reconstructs
16×16 palette-indexed atlas swatches using the exact LAND_DT UVWH and
CLUT mapping: 241 versus 98 for (z=8,x=19), and 243 versus 150 for
(z=11,x=11). Each swatch is fingerprinted using **unaltered PS1
16-bit BGR555/STP values** and shape (the same SHA-256 convention as the
archived `vh_map02_hd_texture_manifest_v23.json`). PNG presentation
expands the 5-bit RGB channels to 8-bit without blur, scaling or color
grading. The STP flag and raw-zero-pixel counts remain in JSON, but **PNG
is not a hardware transparency/semitransparency simulation**.

Use from the remaster repository root (keep output outside Git):

```sh
python3 -m tools.map02_texture_pixel_proof   --disc-image /path/to/owned/game.bin   --layout mode2-2352   --output-prefix /tmp/map02-prs-vs-dat
```

It creates `/tmp/map02-prs-vs-dat.png` (two rows, PRS left,
DAT right) and `/tmp/map02-prs-vs-dat.json` with panel coordinates,
CLUT/UVWH, zero/STP sample counts, all four source-pixel fingerprints
and verification flags. Neither the raw disc nor texture atlas are
written to GitHub. Existing output is not overwritten.

**Fail-closed default:** PNG generation requires matching archived
compressed and decompressed PRS hashes, the full DAT hash, the atlas
hash, LAND_DT hash, exact PRS/DAT two-byte signature, and each of four
decoded pixel hashes. The explicit `--allow-unverified-source`
override allows exploratory previews of different disc editions; the
JSON still reports `all_archived_evidence_matches: false` and
identifies every failed check. This is a source UV-space reference only.
It cannot prove screen-space placement, 3D visibility, the final GPU
composite, or the artistic merit of PRS vs DAT.

Six synthetic regression tests verify nibble order, CLUT lookup,
raw-color SHA-256, PNG contents/panel positions, strict provenance
rejection and EDC-failure handling. They do not require or embed
original game pixels.
