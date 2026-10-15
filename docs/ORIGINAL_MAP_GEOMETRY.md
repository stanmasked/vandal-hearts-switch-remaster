# Original map 11 geometry: source-backed format and safe inspection

**Pinned source:** `HalmyLyseas/VandalHearts-PcPort` at
`14552fffa0e0b47e02b57592e274fc6e7a649923`.

This is the **next integration stage after the confirmed virtual-SD private
texture-patch NRO**. Texture resources (F_TEX01.DAT and LAND_DT.DAT) were
previously tested in NeXium, but that rendered only ONE authored UV patch.
A genuine terrain scene also needs **M_MAP02.PRS**, its unpacked vertex
model/face data and the original game camera/GTE lighting/projection.

## Original memory layout (not a new format)

The original `src/states/game_setup.c::LoadMap` map-number **11** branch
calls `LoadCdFile(CDF_M_MAP02_PRS, 1)`, followed by
`ProcessMapFileData` in `src/maps/unpack.c`. Map 11 has a 28×12
**stored** tile slab, 24×12 **active** map, with margins 11/5.
The original renderer's `RenderMapTile` in `src/core/graphics.c`
uses the following `include/field.h::MapTileModel` fields:

| Field | Original type | Bytes |
|---|---|---:|
| vertices | `SVECTOR[22]`: 4 signed LE 16-bit words (x,y,z,pad) | 176 |
| gfx | `s16[18]`: local map texture index | 36 |
| faces | `u8[18][4]`: four vertex indices per face | 72 |
| shades | `u8[18]`: lighting selector | 18 |
| faceCt | `u8`: active faces, max 18 | 1 |
| height | `u8` | 1 |
| **One tile** | | **304** |

A 28×12 map-11 tile prefix occupies **102,144 bytes**. Some original
decompressed files may contain other backing rows/data; only the
verified **28×12 prefix** is selected for inspection, not interpreted
as an exact required full PRS output size.

The original `LoadMap` adds `GFX_MAP_TEXTURES_OFS` to positive local
indices after decompression. Our inspection reports **unshifted** local
index values from the original file; 0 indicates no texture. A valid
index between 1 and 256 can select one of LAND_DT's 257 UV/CLUT slots
(0..256), but a nonlocal CLUT ID cannot be reconstructed solely from
LAND_DT. The original GPU render path also uses geometry projection
(`gte_rtpt`/`gte_rtps`), backface and depth tests, shade lighting,
per-face UVWH, a texture page and a CLUT; no such live scene is
re-created by this inspector.

## Compressed PRS handling

`src/maps/unpack.c::UnpackMapFileData` uses a 1024-byte zeroed scratchpad
cache initially positioned at **990**. Compressed bytes are prefixed by
a little-endian 32-bit encoded-byte count. Eight LSB-first flag bits
select literal bytes or commands with (a) a 10-bit absolute cache
position, (b) a short relative cache distance or (c) an inline run of
8..71 literals. A zero control byte terminates the stream.

The original C function takes a compressed length but does NOT take
an output buffer size. `tools/decode_vh_map_prs.py` independently
implements this exact cache/flag algorithm with **2 MiB hard input and
output caps**, command bounds and malformed/truncated stream checks.
This decoder is validated using **synthetic PRS streams** and is not
yet verified against the user's actual `M_MAP02.PRS` bytes.

### Offline commands for legally extracted files

Summarize the compressed stream without writing proprietary geometry:

```bash
python3 tools/decode_vh_map_prs.py /private/game/DATA/M_MAP02.PRS \
  --min-decoded 102144
```

Inspect an individual terrain cell and join original LAND_DT UV/CLUT
records in-memory (no public asset upload):

```bash
python3 tools/inspect_vh_map_geometry.py \
  /private/game/DATA/M_MAP02.PRS --prs \
  --x 6 --z 3 \
  --land /private/game/DATA/LAND_DT.DAT
```

Or use `inspect_vh_map_geometry.py` **without** `--prs` on an exactly
102,144-byte extracted, decompressed map-11 model prefix. Inputs are
read-only, and the tools print **metadata, vertex positions, face
indices and CLUT/UV lookup only**—not textures or retail image bytes.

## Regression evidence and remaining gates

Asset-free tests verify: exact `MapTileModel` byte offsets;
height/face count, four-vertex indexing, local GFX and corresponding
LAND_DT UV/CLUT association; rejection of broken records; and
bounded PRS literal/relative/absolute/cache/run decoding with malformed,
truncated or oversized streams and a complete synthetic 102,144-byte
model slab. Both suites are part of the pinned NRO CI preflight and
`make test`. Actual CI confirmation is recorded separately in the
`docs/UPSTREAM_DRAWOTAG_SWITCH_AUDIT.md` journal when green.

**Not achieved yet:** a successful PRS decode of authentic
`M_MAP02.PRS`, identification of every face in the user's own data,
a native multi-face geometry frame through original `RenderMapTile`,
or a real gameplay frame/physical Switch run. Those stages require
owner-provided input and further native integration; this report
does not claim they are complete.
