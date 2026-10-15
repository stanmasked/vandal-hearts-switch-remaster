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
