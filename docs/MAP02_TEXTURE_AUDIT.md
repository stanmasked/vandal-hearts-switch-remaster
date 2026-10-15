# Map 02 LAND_DT / GFX 241–243 audit

Status: **superseded for resource attribution by [M_MAP02 PRS/DAT reconciliation](MAP02_PRS_DAT_RECONCILIATION.md). Do not generate replacement textures from guessed palettes.**

**Critical scope distinction:** The `tools/check_map02_raw.py` check is specifically for zero-based LAND_DT **block 2**. The prior source-disc audit associates the resource `M_MAP02.PRS` with runtime map number **11**, using LAND_DT block **11**. A passing block-2 test cannot establish missing/transparent textures for resource `M_MAP02`. Its recorded nonzero PRS GFX slots (241/243) and the DAT alternatives (98/150) require runtime tracing before assigning a visual defect. See [reconciliation](MAP02_PRS_DAT_RECONCILIATION.md).\n\nThis note records the evidence available from the ongoing map-02 investigation. It is a working audit, **not** proof that either face is intended to be visible.

## Observations to preserve

| Map | GFX | Face in tile | LAND_DT entry | Observed LAND_DT attributes |
| --- | ---: | --- | ---: | --- |
| 02 | 241 | tile 243, face 0 | 641 | UV coordinates = 0, size = 0, palette index = 0 |
| 02 | 243 | tile 319, face 0 | 643 | UV coordinates = 0, size = 0, palette index = 0 |

- The model references both GFX records on active faces; they are not merely unused table slots.
- Adjacent tiles also reference other GFX indices, so the finding does **not** establish that a whole region shares one missing texture.
- In the PC port's rasterization path, pixel value `0x0000` is skipped. This is consistent with transparent/invisible faces but does not independently prove authorial intent.
- The earlier `map02_gfx241_243_clut_decoded.csv` identified CLUT indices 35 and 33. Subsequent mapping established that those CLUTs belong to **map 11**, not map 02. They must not be used as map-02 color evidence.

## Working hypotheses

1. **Intentional empty/hidden faces:** valid geometry uses placeholder texture records to suppress drawing.
2. **Parser/offset or table-association error:** faces are real but the map-to-LAND_DT association is wrong.
3. **Map-specific indirection:** an alternate texture bank, overlay or index translation supplies the actual data.

The observations alone do not distinguish these cases.

## Verification sequence (read-only)

1. Record the source image identity and hash locally. Keep proprietary images and extracted textures outside version control.
2. Re-extract map 02 model faces and LAND_DT independently of any earlier CSV; record byte offsets and index base (0-based vs 1-based).
3. Confirm references for tile 243 / face 0 → 241 → entry 641 and tile 319 / face 0 → 243 → entry 643 using both raw bytes and decoder output.
4. Decode the complete records, including UV, size, palette index, flags and neighboring entries. Preserve hex dumps and the parser's endian/stride assumptions.
5. Cross-check which map owns CLUT 33 and 35 and re-confirm their association with map 11, not map 02.
6. Trace the runtime renderer from the model face to the texture lookup and skip conditions; inspect whether zero-size textures are ignored, transparent, or redirected.
7. Compare screenshots for map 02 against the source game, examining whether those two faces are visible. Only then classify the records as intentional, a parsing error, or unresolved.

## Reproducible raw-byte check

Run the commands from the repository root, using your own legally obtained local extraction:

```sh
python3 -m unittest discover -s tests -p 'test_check_map02_raw.py'
python3 -m tools.check_map02_raw /local/path/LAND_DT.DAT
# Or when the 1797-byte map-02 block has already been extracted:
python3 -m tools.check_map02_raw /local/path/map02.bin --block
```

The check now reports both the full input SHA-256 and the selected map-block SHA-256, along with absolute texture-record and CLUT-index byte offsets. For a full LAND_DT stream, map 02 has zero-based block offset `2 * 1797 = 3594`; for a separately extracted block, the offset is zero. Keep the block fingerprint with visual evidence to avoid comparing different game builds or extraction revisions. A matching fingerprint still does not independently prove that a separately supplied block truly came from map 02.\n\nThe check prints a SHA-256 fingerprint and reports whether the **four raw texture-record bytes** and the separate CLUT-index byte are zero for GFX 241 and 243. A PASS does not establish the correct map index in the original disc, palette interpretation, renderer behavior, or intentional invisibility. In `--block` mode the input is assumed to be map 02; the tool cannot verify that provenance independently. Keep the input file, its provenance, and the emitted report together outside version control. Do not treat the two zero records as a reason to paint over geometry. All-zero synthetic fixtures test error detection only, not real game assets.

## Acceptance criteria for a fix

- Two independent readings (raw data + parser) agree on offsets and indexing.
- The correct source map and palette have been established; **no map-11 CLUT is silently repurposed**.
- A before/after comparison demonstrates a concrete rendering improvement without altering collision, map geometry, or neighboring faces.
- Tests catch the regression and identify the exact map, tile, face, GFX index and LAND_DT entry.
- Both restoration tracks remain separate: **Original Style HD** preserves original appearance; **Modern HD Remaster** is optional and must not be treated as source-accurate.

## Current decision

**Do not patch GFX 241 or 243, assign guessed UVs, or upscale fabricated imagery. Treat zero-based block-2 placeholder evidence as irrelevant to `M_MAP02` until a verified runtime association says otherwise.** The next technical result must come from validating the raw association/renderer behavior and original-game comparison. This document contains no copyrighted game assets.
