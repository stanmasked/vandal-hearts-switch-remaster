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

## Switch-native raw map-bank integration gate (2026-10-16)

A further synthetic test now exercises the real original **raw terrain page upload**
path, not only offline PNG decoding or the separate TIM path. Code commit
[`c612af33`](https://github.com/stanmasked/vandal-hearts-switch-remaster/commit/c612af3343fe22f7fe3cc73d96103b0407a25b58)
adds a strictly synthetic, asset-free 32768-byte F_TEX-format 4bpp VRAM page
and a 1797-byte LAND_DT-format map record with local CLUT ID 32. Both the
raw 4bpp page at (320,0) and the 512-byte CLUT at (672,496) are uploaded
through **original pinned `LoadImage`**. An original
`SetSprt → DR_MODE → AddPrim → DrawOTag` draw samples UV(16,16) and the
first local palette row at native position (8,7). The existing synthetic
15bpp STP test overlaps two pixels of the large 4bpp upload region; its
small 15bpp fixture is intentionally re-uploaded **after** the large
page to preserve prior smoke expectations. All guest resource data is
generated in the C test source, not extracted from the retail game.

**Verified:** [GitHub Actions #38818976526](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38818976526)
at commit `a877d4aa642315e2f928970940ea5005bda70893`
passed both cross-compile and native NeXium emulator jobs. Its preflight
reports **15 DrawOTag checks, 15 bounded TIM checks, 13 raw map-bank checks
(43 total), all OK**. Both 1280×720 capture frames show exact
**(255,0,0)** red and **(0,255,0)** green from the new raw bank at
(835,630)/(910,630). The original standalone TIM-path checks and all
earlier ABR/texture-window checks also remain passing. 5,447 sampled
pixels changed between screenshots due to animated background.

**Boundary:** This proves the **data format → LoadImage → VRAM →
SPRT/DR_MODE → original DrawOTag** contract using synthetic resources.
No actual `F_TEX01.DAT`, `LAND_DT.DAT`, retail texture or live map geometry
has been rendered by the Switch NRO. Real map appearance additionally
requires the selected `gGfxTPageCells`, per-slot UVWH, CLUT selector,
render primitives, camera and lighting. The previous local game-image
audit identifies map 11, texture slot 241 (global GFX 641) as a
candidate with local CLUT 35 and texture-page cell 5; these are
**file/revision-specific source-audit findings**, not a native scene capture.
