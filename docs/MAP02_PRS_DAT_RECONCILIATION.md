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
