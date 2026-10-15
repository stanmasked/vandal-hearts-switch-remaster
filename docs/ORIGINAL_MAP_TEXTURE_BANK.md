# Vandal Hearts — original map texture banks (user-owned data)

## Source-confirmed layout

Pinned upstream source: `HalmyLyseas/VandalHearts-PcPort` at
`14552fffa0e0b47e02b57592e274fc6e7a649923`,
`src/states/game_setup.c::LoadMapTextures` (lines 1216–1400).

The selected `F_TEXxx.DAT` is **not TIM**. It has **32768 bytes** of raw
4-bit indexed pixels: 64 VRAM halfwords/row × 256 rows × 2 bytes/halfword,
uploaded by original `LoadImage` to VRAM (320,0) with RECT (64,256).
That corresponds to a 256×256 texel page in 4bpp mode.

`LAND_DT.DAT` has 69 contiguous **1797-byte** map records. Record #N starts
at byte `N * 1797` and holds:

| Record-relative offset | Length | Payload |
| ---: | ---: | --- |
| 0 | 1028 | 257 `gGfxSubTextures` entries, four bytes each (U,V,W,H) |
| 1028 | 257 | 257 local texture CLUT ID selectors |
| 1285 | 512 | 16 CLUT rows × 16 BGR555 colors × 2 bytes |
| **Total** | **1797** | |

The original game uploads those 512 palette bytes to VRAM
`(672,496)` RECT `(16,16)`, and assigns `gClutIds[32..47]`
to those 16 rows. CLUT ID **32** selects the first row, **35** the fourth
row, etc. Other CLUT selectors may refer to palettes loaded separately
(e.g. `COL_DAT.DAT`); the tool does not guess replacement palettes.

For PS1 4bpp, the **low nibble** of each byte corresponds to the leftmost
texel. A palette index of zero is **not necessarily transparent**: it is
the decoded BGR555 palette color *word* `0x0000` that is transparent.
The preview preserves this distinction: alpha 0 only for raw color 0,
alpha 255 otherwise. STP/ABR semi-transparency needs original raster logic,
not ordinary PNG alpha.

## Local inspection and preview (no assets committed)

For an **already extracted** game file pair:

```bash
python3 tools/inspect_vh_map_texture_bank.py \
  --texture /private/game/DATA/F_TEX01.DAT \
  --land /private/game/DATA/LAND_DT.DAT \
  --map 11 --slot 241 --preview-png /private/map11_slot241.png
```

For the **user-owned raw 2352-byte-sector BIN** from the previously audited
Russian v1.6 disc layout:

```bash
python3 tools/inspect_vh_map_texture_bank.py \
  --raw-bin /private/game/Vandal_Hearts_RU_v1.6.bin \
  --texture-lba 4374 --land-lba 4954 --map 11 \
  --slot 241 --preview-png /private/map11_slot241.png
```

The LBA values **are specific to the audited image**, not universal
offsets for every release. The extractor confirms the 12-byte CD sync
pattern, Mode 2, two identical XA subheaders, Form 1, complete sector
range and exact requested payload byte length; it does not run an ISO9660
directory parser. It consumes the 2048-byte payload at offset +24 from
each 2352-byte sector. If the image is a 2048-byte ISO or another release,
do not reuse these offsets without independent verification.

A PNG preview depicts the **entire 256×256 source atlas using the selected
slot's palette**, not an authentic map camera, polygon mapping, lighting
or final game frame. `--slot 241` selects local palette ID 35 in the
previously audited map 11 data, but this is release-specific. Other slots
can use different CLUTs. The tool never modifies the BIN or DAT files.
Output JSON includes individual SHA-256 digests for provenance.

Previous private-source audit of the RU v1.6 image recorded (not enforced
across other retail revisions):

- `F_TEX01.DAT`: LBA 4374, 32768 bytes,
  SHA-256 `a3c6db4516930cdb2555cf7cda2456bcd118e5ec46737e2c320431d7b9a63b75`
- `LAND_DT.DAT`: LBA 4954, 123993 bytes,
  SHA-256 `e91891bad10efbc58ee010a52740c1510383529fcbf24eec3783e344cbcf773b`

## Validation boundaries

`make test` runs asset-free unit tests for DAT record bounds,
little-endian CLUTs, PS1 nibble order, BGR555 colors, nonzero CLUT index
zero, rendering a synthetically generated PNG, raw Mode-2/Form-1 sector
boundaries, corruption and truncation. The pinned Switch workflow performs
these tests before its expensive SDL2/NRO compilation.

**No game ROM, audio, textures, palettes or transformed artwork is in this
repository.** A verified PNG from a user's actual image proves the offline
atlas decoding stage; a real GPU frame requires connecting these bytes to
`LoadImage`, CLUT setup and original map geometry in the NRO, followed
by separate NeXium and hardware evidence.
