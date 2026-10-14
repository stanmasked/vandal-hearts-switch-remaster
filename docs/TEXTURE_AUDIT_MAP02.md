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
