# Vandal Hearts texture audit — map 02 slots 641 and 643

**Status:** evidence recorded; visual impact and intended semantics remain unconfirmed.  
**Scope:** map 02, active model faces using GFX 241 and GFX 243.

## Confirmed observations

The current audit report identifies two active faces whose texture-table entries in map 02 look like empty placeholders:

| GFX | Face | Tile | LAND_DT entry | Texture coordinates | Dimensions | Palette |
|---:|---:|---:|---:|---|---|---:|
| 241 | 0 | 243 | 641 | (0, 0) | 0 × 0 | 0 |
| 243 | 0 | 319 | 643 | (0, 0) | 0 × 0 | 0 |

The surrounding geometry uses different GFX indices: tiles 242 and 244 use GFX 78 and 95; tile 318 uses GFX 145 and 207. GFX 241 and 243 are reported to be within the active part of the map models.

The same slot numbers have non-empty records in other LAND_DT blocks. Reported examples include slot 641 with texture region 160 × 224, dimensions 16 × 24, palette 40, and slot 643 with region 184 × 208, dimensions 16 × 24, palette 40. Such records reportedly occur in 17 other map blocks.

The upstream PC renderer documentation is reported to specify that texture pixels with value `0x0000` are skipped during rasterization. This makes missing/transparent output a plausible hypothesis, but it does not establish that these map 02 faces are visibly defective in the original game.

## Interpretation

The evidence points to a **map-block-specific data difference**, not a universally empty texture slot. It does not yet distinguish between:

1. an intentional empty/transparent face in map 02;
2. a map-specific texture-table encoding or sentinel convention;
3. a lost or mis-associated texture reference during extraction/preparation;
4. a rendering detail that is visually masked or not apparent in ordinary gameplay.

The fact that the faces are active in geometry makes them worth investigating, but active geometry alone does not prove that a visible texture should be present.

## Safe next checks

1. Compare the raw map 02 texture-table bytes for entries 641 and 643 with the corresponding records from the 17 other blocks. Record offsets, field widths, endianness, and any block-relative addressing before interpreting values.
2. Trace how the extractor parses zero-sized records. Check whether zero width/height is preserved from the source or introduced by a failed bounds check, missing payload, or region-base calculation.
3. Compare the map 02 geometry/material references and neighboring records against at least one known-good map block. Do not copy texture coordinates, dimensions, or palette values merely because the slot numbers match.
4. Render diagnostic views of tiles 243 and 319 with face IDs, GFX IDs, UVs, texture-slot IDs, and bounds overlaid. This can verify the pipeline's interpretation, but it cannot replace comparison with the original game's appearance.
5. If legally available, inspect the corresponding scene in the original game or a trusted reference capture. Confirm whether these faces are meant to be invisible, transparent, or textured before changing data.
6. Add a regression fixture for these records only after the source bytes and expected interpretation are understood.

## Decision

**Do not substitute slots 641 or 643 from another map yet.** Keep the extracted/source data unchanged and mark both records as unresolved. Any repair should be based on source-byte tracing plus visual evidence, then checked against neighboring geometry and other maps to avoid introducing a false texture or incorrect palette.

## Evidence boundary

The slot values, tile/GFX associations, and count of other blocks are recorded from the ongoing audit report. This note does not independently validate the original disc bytes or confirm a visible in-game defect. No source game data or extracted copyrighted assets are included in this repository.


## Upstream loader cross-check (2026-10-15)

At upstream PC-port commit [`14552fffa0e0b47e02b57592e274fc6e7a649923`](https://github.com/HalmyLyseas/VandalHearts-PcPort/commit/14552fffa0e0b47e02b57592e274fc6e7a649923), `src/states/game_setup.c` contains `LoadMapTextures()` (lines 1216–1400). The loader:

- loads `CDF_LAND_DT_DAT`;
- selects the map's block with `pFileData = &gScratch3_80180210[gState.mapNum * 1797]`;
- reads four bytes per entry into `gGfxSubTextures[i][0..3]` for 257 map-texture entries;
- then reads a CLUT index for each entry, reads 512 bytes of CLUT data, and resolves the CLUT and texture-page IDs.

This is a useful independent cross-check: the upstream runtime consumes map-specific records from a fixed 1797-byte block and copies the four per-entry values directly into its texture-subtexture table. It does **not** prove what the four values for map 02 slots 641/643 should be, nor whether the observed zero-sized records are intentional. It also does not establish whether the current extraction tool preserved the source bytes correctly.

Source: [upstream `game_setup.c` at the audited commit](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/src/states/game_setup.c#L1216-L1400).

### Revised priority

Before attempting visual repair, compare the exact raw 1797-byte block for map 02 with the corresponding blocks from known-good maps and verify the parser's byte offsets against the upstream loader layout. In particular, confirm whether “slot 641/643” refers to the same table indexing in the extracted representation as in the upstream `gGfxSubTextures`/CLUT arrays. Keep the two records unmodified until that mapping and the source bytes are validated.


## Texture-index mapping cross-check (2026-10-15)

A second upstream source check resolves one indexing ambiguity. In `include/graphics.h`, the enum declares `GFX_MAP_TEXTURES_OFS = 400` and `GFX_MAP_TEXTURE_1 = 401`. `LoadMapTextures()` iterates table indices 400 through 656 (257 entries) while reading the 257 four-byte subtexture records from the selected 1797-byte map block.

Therefore the observed relationship is consistent with the upstream table layout:

- GFX 241 → table index `400 + 241 = 641`
- GFX 243 → table index `400 + 243 = 643`

This supports that 641 and 643 are the corresponding **runtime subtexture-table indices** for GFX 241 and GFX 243, rather than a simple off-by-one introduced by that particular naming convention. It does not independently prove the extraction tool's raw-byte offsets, or establish whether the map-specific zero records are intentional.

Sources:
- [`include/graphics.h` at the audited upstream commit](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/include/graphics.h)
- [`LoadMapTextures()` at the audited upstream commit](https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/src/states/game_setup.c#L1216-L1400)

### Outcome of this check

**Confirmed:** the GFX-to-runtime-table-index arithmetic matches the reported slots exactly.  
**Still unresolved:** whether the four source bytes for map 02 entries 241 and 243 are zero in the original data, whether zero dimensions are intentional, and whether either face is visibly defective in the original game.


## Raw block-offset calculation from the upstream loader (2026-10-15)

The loader's byte-level read order makes it possible to calculate where these records must reside in a LAND_DT block, without claiming that the original bytes have been inspected. LoadMapTextures() reads 257 records of four bytes each in ascending table-index order, beginning at table index 400. Therefore record ordinal equals the GFX index, and the four-byte record starts at GFX * 4 within the selected 1797-byte block.

| GFX | Runtime table index | Record ordinal | Offset within block | Four-byte range |
|---:|---:|---:|---:|---|
| 241 | 641 | 241 | 964 (0x3C4) | 964–967 (0x3C4–0x3C7) |
| 243 | 643 | 243 | 972 (0x3CC) | 972–975 (0x3CC–0x3CF) |

The 257 four-byte records occupy bytes 0–1027. The following 257 CLUT-index bytes occupy offsets 1028–1284, followed by 512 CLUT-data bytes at offsets 1285–1796. This exactly accounts for the loader's documented 1797-byte block size.

For map number 2, the loader's block base expression mapNum * 1797 gives a base offset of 3594 (0xE0A) relative to the beginning of the LAND_DT data loaded into the scratch buffer. Under that map-number assumption, the two record starts would be 4558 (0x11CE) and 4566 (0x11D6) relative to that loaded data. These are calculated offsets, not observed bytes or verified file offsets on disc.

### Why this matters

This narrows the next verification to a small, deterministic byte range and provides a way to compare the parser's output with the upstream layout. A raw dump or extractor output can be checked at these offsets; if the four source bytes are nonzero while parsed metadata becomes zero, the extraction/parsing stage becomes the leading suspect. If they are zero in the source block too, that still does not by itself establish whether the record is intentional or visually defective.

**Evidence boundary:** no original LAND_DT binary, disc image, or extracted block was available in the repository files inspected during this check. No byte values have been read or asserted here.


## Reproducible raw-record inspection tool (2026-10-15)

Added `tools/inspect_land_dt.py` to report raw four-byte records and CLUT-index bytes for GFX 241 and 243. It supports either a concatenated LAND_DT stream (`--map-number 2`, using zero-based block indexing) or a single extracted 1797-byte block (`--block`). It reports offsets and byte values as JSON and explicitly warns that metadata alone does not prove a visual defect.

Added `tests/test_inspect_land_dt.py` with synthetic data tests for the selected block, expected offsets, raw bytes, CLUT indices, single-block mode, and invalid input sizes/map selection. `make test` now includes this test file. These are tests against synthetic fixtures; they do not validate any original game asset because no LAND_DT binary was available in the repository.


## Expanded GFX comparison support (2026-10-15)

The raw inspector now accepts arbitrary GFX indices through `--gfx`, while retaining 241 and 243 as defaults. This allows the same raw-data procedure to compare the map 02 suspect records against neighboring GFX entries without changing the source data. For example:

```sh
python3 tools/inspect_land_dt.py path/to/LAND_DT.DAT --map-number 2 --gfx 78 95 145 207 241 243
```

For one extracted block, use `--block --gfx 78 95 145 207 241 243`. Valid indices are 0–256. The tests include synthetic custom-index fixtures and invalid-index handling. These changes improve repeatability; they do not resolve the original asset question until real source bytes are supplied or lawfully extracted and inspected.


## Cross-map raw-record comparison mode (2026-10-15)

Extended `tools/inspect_land_dt.py` with `--compare-maps`. It compares selected GFX records and their CLUT indices across two or more zero-based blocks in the same concatenated input, and marks whether each selected GFX record differs between the chosen maps. Example:

```sh
python3 tools/inspect_land_dt.py path/to/LAND_DT.DAT --compare-maps 2 3 4 5 --gfx 78 95 145 207 241 243
```

The comparison is intentionally byte-level: a difference is evidence of map-specific data, not proof that any record is corrupt or that another map's record is the correct replacement. The synthetic tests cover differing and identical records, CLUT index differences, and invalid map selections. CI execution is pending for this latest change.
