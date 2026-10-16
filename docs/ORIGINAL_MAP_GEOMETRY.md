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

## Native owner-only two-face geometry bridge (acceptance candidate)

A newly added NRO branch can consume a THIRD optional, private SD file:

`sdmc:/switch/vandal-hearts-remaster/private-assets/MAP11_MODELS_28X12.BIN`

This is the **decompressed 102144-byte map-11 tile prefix**, not the
original `M_MAP02.PRS` bitstream. The source `source/vh_private_map_geometry.c`
checks its exact size, all 336 `MapTileModel.faceCt <= 18` constraints
and every active face's 4 vertex references (must be 0..21)
**before** replacing the output model. Missing geometry leaves the
previously accepted private, single-patch screenshot unchanged.
Partial, corrupt or incompatible geometry rejects the source rather
than silently drawing arbitrary vertices.

To stage the *user-owned* compressed PRS safely, after the existing
F_TEX01/LAND_DT bank is already present on the local Switch SD:

```bash
python3 tools/stage_vh_private_map_geometry.py \
  --prs /private/game/DATA/M_MAP02.PRS \
  --sd-root /path/to/mounted/switch-sd
```

Or use an exactly 102144-byte, already decompressed map prefix:

```bash
python3 tools/stage_vh_private_map_geometry.py \
  --unpacked /private/game/MAP11_PREFIX.BIN \
  --sd-root /path/to/mounted/switch-sd
```

The tool validates all tile/face references, refuses to overwrite
previously staged output, and keeps the map bytes **only on the local
SD card**. A metadata-only SHA-256 manifest records the local byte set.

If the private NRO finds both original texture files and the optional
unpacked model file, it extracts **tile (6,3)**, reads its source face
`gfx[]` IDs and vertex indexes, looks up each local face's individual
UVWH and CLUT selector in the **same LAND_DT** table, and submits
multiple original `POLY_FT4` primitives via `DrawOTag`.

**Strict limitation:** the preview uses an explicitly simplified
orthographic coordinate transform
`screen_x=6+vertex_x/8`,
`screen_y=4+vertex_z/8-vertex_y/16`
inside the 12×9 test framebuffer. This is a **geometry/data-path
acceptance probe**, NOT the game's original GTE perspective projection,
backface tests, ordering-table depth, camera, terrain lighting, or
`RenderMapTile`. It draws only locally mapped CLUT 32..47 faces from
a selected tile. If a source face uses an external GFX page or CLUT,
the preview does not pretend to be the original scene.

The synthetic CI counterpart provides tile (6,3) with two adjoining
flat model faces, independently selects local GFX slots **241 and 242**
and uses two distinct local CLUT rows **35 and 36**. The image
acceptance checks red/blue on the left face and magenta/cyan on the
right to prove original vertex indexes and per-face GFX lookup.
The original private four-quadrant UV probe is run FIRST without a
geometry file, so regressions can be isolated from the new renderer.

As of creation this native multi-face candidate has not yet been
confirmed by a finished NeXium screenshot run. That evidence must be
recorded before changing the test's status to accepted. The user's
authentic `M_MAP02.PRS` is still unavailable in CI; no copyrighted
map bytes are in any public artifact.

## Confirmed source-model two-face NRO preview (CI #38825754507)

The two-face native geometry **acceptance gate is now passed**:
[GitHub Actions #38825754507](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38825754507)
at integration commit `ddf891a0f54cc4be310f0837160615c3df36f5a3`
completed all **three jobs SUCCESS**: Switch NRO compile, standard original
DrawOTag raster NeXium, and synthetic private SD NeXium.

Two runs of the **same NRO executable**, using independent staged
files under the same isolated virtual SD root, produced:

1. With only F_TEX01 + LAND_DT (geometry missing), the prior one-patch
   screenshot remained red/green/blue/yellow at all four corners.
2. After staging a complete synthetic `MAP11_MODELS_28X12.BIN`
   (336 × 304 = 102144 bytes), the original C loader decoded tile
   (6,3) with **two source `MapTileModel` faces**. The two
   `gfx[]` references 241 and 242 independently selected
   source UVWH and CLUT selectors 35 and 36. Native original
   `SetPolyFT4 → AddPrim → DrawOTag` produced two adjacent
   polygons at the expected positions.

NeXium 1280×720 screenshot probes for the geometry mode:
`(400,205)=(255,0,0)` **left top red**;
`(880,205)=(255,0,255)` **right top magenta**;
`(400,510)=(0,0,255)` **left bottom blue**;
`(880,510)=(0,255,255)` **right bottom cyan**.
The difference from the single-patch color pattern is deliberate;
it rejects a false success in the earlier private branch. The
two screenshot passes and earlier original TIM, ABR and window checks
were all successful.

New host evidence: **85 Python tests** passed in the NRO workflow
(80 prior plus 5 private geometry staging regressions), and TWO
separate C host test executables passed, including validation of
the complete 336-tile source geometry slab, face count and vertex
indices. The binary NRO0 structure check passed. The private-SD
evidence artifact for this run includes both the original
`map11-synthetic.png` and new `map11-multiface.png`, plus
emulator diagnostics.

**Scope boundary:** This is the first observed **multi-face,
original-format MapTileModel → per-face UV/CLUT → original pinned
POLY_FT4/DrawOTag** synthetic integration in a Switch NRO under
NeXium. The projection remains the explicitly simplified
orthographic preview described above, NOT `RenderMapTile` or the
original PS1 camera/GTE. No game-authored model vertices, actual
`M_MAP02.PRS`, retail terrain scene or physical Switch hardware
were tested. The next gate is user-side validation of an
authentic extracted PRS and then reusing native original map
projection/render logic without publishing copyrighted data.

## Original pinned GTE perspective in the multi-face Switch probe (integration candidate)

The synthetic two-face native map preview has been upgraded from the
previous *arbitrary orthographic math* to the **actual software PS1 GTE
implementation from the pinned PC-port**:
`platform/pc/src/libgte.c` at upstream SHA
`14552fffa0e0b47e02b57592e274fc6e7a649923`.
The Switch workflow cross-compiles and links that original GTE
translation unit alongside its original `libgpu.c` and `pc_raster.c`.
The NRO now calls `InitGeom`, `SetGeomOffset`,
`SetGeomScreen`, `RotMatrix`, `TransMatrix`,
`SetRotMatrix`, `SetTransMatrix` and
`RotTransPers4`. The last function performs RTPT for the first
three source vertices, RTPS for the fourth and AVSZ4 depth
averaging, then supplies four signed packed screen coordinates.

The camera in this isolated 12×9 preview is a **chosen test camera**,
NOT recovered map 11 gameplay camera state: source-space pitch
`SVECTOR(-512,0,0)` in 4096-angle units, translation (0,0,96),
`H=14` and pixel offset (6,4). The first face, whose source
vertices form a rectangle, projects to a trapezoid rather than a
parallel-sided quad; a representative host GTE result is TL=(0,1),
TR=(6,1), near edge x shifting from 0 to 2 at the bottom, and
positive depth index (OTZ~24). This fixture intentionally tests
perspective division and matrix calculations in addition to texture
sampling.

**Important primitive ordering:** exact upstream
`src/core/graphics.c::RenderMapTile` calls
`gte_stsxy3(&poly->x0,&poly->x1,&poly->x3)`, then
`gte_stsxy(&poly->x2)`. Thus source `faces[][2]` maps to
FT4 packet corner **3** and source `faces[][3]` maps to
packet corner **2**. The NRO reproduces this order exactly. Synthetic
source-format face vertex lists use [top-left, top-right, bottom-right,
bottom-left] for the same reason. The prior hand-authored orthographic
probe was limited to demonstration and should not be used as a
reference for vertex packet order.

An asset-free, independent host C test
`tests/test_pinned_map_gte_camera.c` is linked against precisely
the same pinned `libgte.c`; it checks valid four-point perspective,
depth and repeated projection determinism. The private NeXium
screenshot checker samples red, blue, magenta and cyan in the newly
projected two-face scene, plus a red pixel on the **left extension**
that could not have been covered by the old orthographic geometry.
These tests are separate from the established synthetic single-UV-patch
GPU assertions.

**Acceptance status: PASS** — [GitHub Actions #38827488368](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38827488368), at commit `19f063e1cde0010a90458898be2ca7f2fa813712`, passed all THREE jobs:
Switch NRO cross-compilation, ordinary original DrawOTag smoke and private
virtual-SD synthetic map-11 GTE projection. The original `libgte.c`
host regression completed successfully with perspective and positive
OTZ; source-backed MapTileModel validation, PRS and texture checks passed.

The private NeXium scenario first reverified the existing four-color
UV/CLUT patch. Next the SAME NRO loaded the full synthetic 28×12
304-byte map model slab from virtual SD; its original-port `RotMatrix`
and `RotTransPers4` perspective, per-face GFX 241/242 and
CLUT 35/36 displayed the correct 1280×720 screenshot samples:

| Name | Screenshot XY | Observed RGB |
| --- | --- | --- |
| Left top red | (260,210) | (255,0,0) |
| Right top magenta | (850,210) | (255,0,255) |
| Left bottom blue | (400,400) | (0,0,255) |
| Right bottom cyan | (850,400) | (0,255,255) |
| GTE-only near upper edge | (300,125) | (255,0,0) |

The fifth sample is OUTSIDE the old orthographic quad and INSIDE the
GTE-projected trapezoid. Early exploratory CI runs failed on stale
orthographic screenshot point locations, not on GPU build or GTE
math. The green run additionally verifies native NRO0 segments,
85 Python tests, separate host C texture/model validators, and the
host projection test, with no synthetic smoke regressions.

The existing original `RenderMapTile` itself is **not** compiled
into this test NRO: it still requires map state, lighting, camera
objects, graphics arena, backface calculations and ordering-table
depth setup. Similarly, the demonstration camera is not the game's
authentic GTE register state. No PS1 disc bytes or retail terrain
meshes are embedded in the build.

## Signed GTE NCLIP and AVSZ4 depth-sorted map preview (new integration gate)

The latest private Switch NRO preview further approaches the original
`src/core/graphics.c::RenderMapTile` primitive pipeline.
The NRO **no longer calls `RotTransPers4` alone and accepts every
triangle winding**. Instead, the exact pinned `inline_gte.h`
wrapper calls its original GTE software implementation in this order:

```c
gte_ldv3(&v[0], &v[1], &v[2]);
gte_rtpt();
gte_nclip();
gte_stopz(&opz);
if (opz <= 0) continue; /* PS1 front-face test */
gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);
gte_ldv0(&v[3]);
gte_rtps();
gte_stsxy(&poly->x2);
gte_avsz4();
gte_stotz(&otz);
```

The 256-bucket **private test** ordering table is a reduced-capacity
version of the game's own OT mechanism: `ClearOTag(ot,256)`
and `AddPrim(&ot[256-otz],poly)` after bounding OTZ to 5..255.
Since buckets are walked in ascending order, the distant polygons
are submitted first and nearby polygons overlay them. The black
background is inserted at bucket 0. The original game uses a larger
table and additional face shading/camera logic; do not interpret the
256-bucket probe as its full OT.

The synthetic 28×12 model slab now contains **three authored face
records**, of which only two are front-facing: a deliberately reversed
face in the same projected left region uses the alternate slot/CLUT
and would recolor the red/blue surface if it were submitted by a
renderer that neglected NCLIP. It precedes the two forward-facing
faces in source order. A verified frame must retain left red/blue,
right magenta/cyan and the distinctive perspective-only red pixel.
The original file format and palette upload remain unchanged.
The owner-supplied private geometry loader accepts genuine model
slabs with up to 18 faces per tile; it does not fabricate additional
faces for user-provided files.

`tests/test_pinned_map_gte_camera.c` now directly executes
`gte_nclip`/signed `gte_stopz` on both vertex windings using
the very same pinned libgte, and separately cross-checks
`gte_avsz4`/depth. Python staging checks explicitly require the
reversed first face, two forward faces and the exact host→NRO GTE
opcode order and OT bucket index. These checks are asset-free,
with no proprietary game map data in the test fixtures.

**Acceptance: PASS** — [GitHub Actions #38828663571](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38828663571) completed
**all three jobs with success** (Switch NRO cross-compile, original
synthetic GPU raster smoke in NeXium, and private virtual-SD map preview
in NeXium). The C host projection test measured **GTE NCLIP=+30** for
the front-facing sample, **NCLIP=−30** for its reversed twin, and
**AVSZ4 OTZ=24**. All 86 Python tests passed, including the new
source-sequence assertion; the C MapTileModel and file-bank tests also
passed. NRO0 image size/segments were checked.

The private NeXium run first verified the unmodified standalone
four-quadrant texture preview. It then loaded a **three-face** model
slab from virtual SD. The first source face was deliberately reversed
and would paint over the red/blue left quad if NCLIP were missing; the
other two were front-facing, with distinct texture slots/palettes.
The screenshot confirms that **only the forward pair rendered**:
(260,210)=(255,0,0), (850,210)=(255,0,255),
(400,400)=(0,0,255), (850,400)=(0,255,255), and the extra
GTE-only perspective edge at (300,125)=(255,0,0).
This is reproducible using the screenshot and source-model fixtures
published in the CI evidence artifact. The test verifies practical
backface behavior and non-regression of the reduced OT depth path,
although an overlapping near/far geometry fixture is still needed
to independently establish depth occlusion ordering.

This milestone does not yet include the source game's side-light
table, distance shading or actual battle camera state;
nor does it compile the entire original `RenderMapTile` function.

## Adversarial overlapping-face OTZ occlusion acceptance (in progress)

The existing NCLIP smoke test already proves that a reversed
source face never contaminates the front-facing pair. It does **not**
prove near/far ordering, because those faces lie alongside one
another. A separate, synthetic, virtual-SD scenario now checks
occlusion explicitly without changing the old scene.

Two front-facing source `MapTileModel` quads occupy approximately
the **same screen-space silhouette** using the original pinned
`RotMatrix` and GTE perspective. Their world coordinates are
related by the inverse of the test camera's pitch/translation:

```text
near = [(-32,0,-16), (0,0,-16), (0,0,24), (-32,0,24)]
far_i = (2*near_i.x, 2*near_i.y - 68, 2*near_i.z + 68)
```

The `-68` sign is essential for the pinned **negative 45° X
rotation**: the far polygon scales camera-space distance by
approximately two, while preserving the projected footprint.
The synthetic geometry intentionally lists **far first** with
GFX slot 242 / CLUT 36 (magenta/cyan), then **near second**
with GFX slot 241 / CLUT 35 (red/blue). If all faces are
inserted head-first into ONE OT bucket, the far face is drawn
last and incorrectly covers the near face. Using original GTE
`AVSZ4`-derived OTZ bucket indices must instead draw
far first and near second, regardless of insertion order.

`tests/test_pinned_map_gte_camera.c` validates actual pinned GTE
near/far depth separation and near-coincident screen positions.
`tests/test_stage_vh_private_map_geometry.py` guards the exact
source-format two-face geometry and private SD staging. The third
NeXium virtual-SD run uses an **isolated second SD root** and
checks the red upper / blue lower near-face pixels plus the
absence of extraneous right-hand geometry. This is a distinct
regression gate from the existing four-color UV scene and the
three-face NCLIP scene. All fixtures are synthetic.

**Acceptance: PASS** — [GitHub Actions #38829473254](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38829473254),
code revision `32088a872301a9640ca7e23b3ec6307ec6169eef`,
finished **all three jobs successfully**: cross-compilation,
asset-free original GPU NeXium raster and multi-mode private
SD NeXium. The pinned PC-port GTE host test returned
**near OTZ=24, far OTZ=49**, with near-coincident screen
positions. The private NeXium job separately captured
(a) the standalone four-quadrant UV/CLUT texture,
(b) the two-visible-plus-one-reversed NCLIP scene,
and (c) the overlapping far-first/near-last geometry scene
staged in a SECOND isolated virtual SD root.

In the final scene, the actual 1280×720 NeXium screenshot
measured `(260,210)=(255,0,0)` (near red over far magenta),
`(400,400)=(0,0,255)` (near blue over far cyan), and
`(850,210)=(0,0,0)` (empty space). All screenshot
checks passed both in the polling loop and a second independent
post-capture check. The original bank/GTE/model loaders and all
**88 Python tests** passed. No real game data were used.

This independently confirms that the original pinned GTE
depth calculation and the reduced `ClearOTag/AddPrim/DrawOTag`
bucket ordering correctly handle intentional overlapping
source-format faces in the native Switch NRO under NeXium.
It is not evidence of game-authored lighting, real
`M_MAP02.PRS` or a hardware Nintendo Switch test.

## Source-exact distance attenuation after GTE AVSZ4 (pending native screenshot)

Original `src/core/graphics.c::RenderMapTile` shades each
textured face using **two distinct inputs**: the per-side
`gSideLightColor[tileModel->shades[faceIdx]]` RGB
and the GTE-calculated `OTZ`. The distance component is:

```text
shading = clamp(OTZ - 150, 0, 256)
output_component = side_light_component
                 - ((side_light_component * shading) >> 8)
```

The camera may produce OTZ below 150 (no distance fading),
between 150 and 406 (progressive fading), or 406 and
above (fully dark). `source/vh_private_map_shading.h` contains
only this *source-exact arithmetic*. It accepts a caller-supplied
side-light component and does NOT claim to reconstruct the
source game's dynamic 26-entry `gSideLightColor` table.

The native probe now uses `vh_map_distance_component(128, otz)`
for the synthetic terrain faces, after its original pinned
GTE `AVSZ4`. The neutral **128/128/128** side-light input
is chosen strictly for the synthetic fixture; it is not
the real game lighting state. The existing near-face checks
(OTZ 24 and 49) remain unchanged, because they are below
the source's 150 threshold.

`tests/test_private_map_shading.c` independently verifies
84 combinations of RGB input and OTZ, including the exact
thresholds and saturation. A further isolated NeXium
virtual-SD scene generates a source-format polygon at a
distant camera-scaled position (`8*near + (0,-476,476)`),
so its original GTE OTZ rises above 150 but its projected
footprint nearly coincides with the prior test area. This
native scene must show visibly attenuated magenta/cyan
rather than full-intensity primaries.

**Acceptance: PASS** — [GitHub Actions #38830050760](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38830050760)
at source revision `0f6c043113d9123af76af9fb2079b4afdab1cde8`
completed **all three CI jobs successfully**. The pinned original
GTE projection yielded **OTZ=197**, above the original
`RenderMapTile` attenuation threshold. Using a test-only
neutral base color of (128,128,128), the rasterized 1280×720
NeXium screenshot measured **magenta=(206,0,206)** and
**cyan=(0,206,206)**, rather than their non-attenuated 255
values. Both values were independently verified twice.
The source-exact distance formula passed **84 C test cases**
and the full preflight ran **90 Python tests**. The preceding
single UV/CLUT patch, three-face NCLIP demonstration and
overlapping near/far OTZ screenshot tests also passed unchanged.

This confirms actual original-GTE-distance-driven texture
modulation through the pinned rasterizer inside Switch NRO
and NeXium. It is NOT proof of reconstructed game-authored
light directions or intensities.

Original side normals, `UpdateLight`, grid-color overrides
and real game-authored camera values remain out of scope.
