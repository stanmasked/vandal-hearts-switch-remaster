# Software Renderer Contract

## Purpose

`source/software_renderer.h` defines a small platform-neutral software-canvas primitive. It deliberately does not acquire a framebuffer, present a frame, choose a pixel format, or depend on libnx, SDL, OpenGL, or the original game's assets.

## Canvas

A `VhCanvas` contains:

- `pixels`: caller-owned memory holding packed 32-bit pixels;
- `stride_pixels`: distance between the starts of adjacent rows, measured in pixels (not bytes);
- `width` and `height`: visible canvas dimensions.

The caller is responsible for ensuring the allocation covers at least `stride_pixels * height` pixels. The stride must be at least the visible width.

## Rectangle fill behavior

`vh_canvas_fill_rect` fills the intersection of the requested rectangle and the visible canvas. Negative origins and rectangles extending beyond the right or bottom edges are clipped. Empty or wholly off-screen rectangles are no-ops. Null canvas pointers, null pixel storage, non-positive dimensions, and a stride smaller than the width are rejected as no-ops.

The color is copied unchanged into each covered pixel. Its channel ordering and alpha representation are intentionally platform-defined by the caller; the renderer does not convert colors.

Bounds are widened during arithmetic to avoid signed integer overflow when adding large coordinates and dimensions.

## Tests

Run `make test` to execute both the tactical-rule/input tests and `tests/test_software_renderer.c`. The renderer tests cover ordinary fills, padded row strides, clipping at all relevant edges, off-screen and empty rectangles, malformed canvas inputs, rectangle outlines clipped at negative origins, and coordinates near `INT_MIN`/`INT_MAX`.

## Pixel and line primitives

- `vh_canvas_put_pixel` writes one pixel only when its coordinates are inside the visible canvas.
- `vh_canvas_draw_hline` and `vh_canvas_draw_vline` draw clipped horizontal and vertical lines using a positive length and a starting coordinate. The implementation shares rectangle-fill clipping, so partially off-screen lines are clipped and invalid lengths are no-ops.
- All primitives honor `stride_pixels` and leave row padding untouched.

- `vh_canvas_draw_rect_outline` draws a one-pixel border around a rectangle with the requested width and height. The same clipping and stride guarantees apply; non-positive extents are no-ops. Coordinate arithmetic for the far edges is widened before use.

The host-side renderer tests cover valid and out-of-bounds pixel writes, clipped horizontal/vertical lines, rectangle borders and untouched interiors, extreme integer coordinates, and padding preservation. `make test-sanitize` runs the same tests with AddressSanitizer and UndefinedBehaviorSanitizer when the host compiler supports them.

## Current limitation

The Switch prototype still owns framebuffer acquisition and presentation in `source/main.c`. This contract only isolates the rectangle rasterization primitive; it is not a complete rendering backend and does not yet render the original Vandal Hearts game.


## Textured FT4 diagnostic path

`source/ft4_textured_quad.h` is a portable, self-contained CPU
reference rasterizer for textured `POLY_FT4` quadrilaterals. It
accepts a screen-space four-corner face perimeter, a caller-supplied
UVWH crop and an already decoded packed RGBA32 source texture. The
helper `vh_ft4_from_face_perimeter` maps original Vandal Hearts
terrain face vertices to PS1 GPU corner order:

```text
face perimeter [0, 1, 2, 3] → GPU [0, 1, 3, 2]
GPU uv0=(u,v)  uv1=(u+w,v)
GPU uv2=(u,v+h)  uv3=(u+w,v+h)
```

The quad is split into the two FT4 triangles (0,1,2) and (1,3,2),
rasterized at pixel centers with affine barycentric interpolation and
nearest-neighbor texture sampling. It accepts either polygon winding
and clips to the framebuffer bounds before integer conversion.
Texture dimensions/stride, coordinates and invalid inputs are checked;
destination row padding must remain untouched.

The native Switch prototype's `source/main.c` now renders two
**synthetic** 16×16 UV diagnostic samples in its right-hand panel,
one with normal face ordering and one mirrored. Both use the portable
rasterizer on the actual libnx framebuffer. This is a graphics plumbing
test, not a claim that the original MAP02 geometry or its art has been
loaded into the running game.

The host suite builds `tests/test_ft4_textured_quad.c`, including
pixel-exact orientation tests with asymmetric textures, the MAP02
(240,192) and (240,208) 16×16 crops, mirror handling, clipping, stride
padding, invalid inputs and degenerate polygons. GitHub Actions verifies
the portable rasterizer, and the Switch toolchain workflow builds a
native NRO. `make test-sanitize` also exercises the tests under
ASan/UBSan where supported.

**Limitations:** the rasterizer does not implement PS1 GTE screen-space
projection, depth buffering/ordering tables, perspective corrections,
texture-page windows, dithering, vertex shading, or PS1 hardware
semi-transparency modes. It can now omit fully transparent source texels
and route STP-flagged pixels through a caller-selected blend callback.
It samples decoded RGBA32 with a separate texel-class mask rather than
reading 4-bit indices directly inside the triangle loop. Quads remain
diagnostic affine approximations and cannot establish pixel-identical
correspondence to a real PlayStation capture. No original game assets
are embedded in the binary.


## PS1 4-bit indexed atlas and CLUT-to-FT4 bridge

The native Switch prototype now exercises a **complete synthetic
indexed4-to-polygon color path**, implemented without embedding any
original game textures. The portable `source/ps1_indexed_texture.h`
decoder reads 4-bit packed atlas texels and their 16-color little-endian
BGR555 CLUT entries. Even logical u selects the low nibble of the atlas
byte; odd u selects the high nibble. This exactly matches the atlas
coordinate convention used by the MAP02 forensic Python tooling.

The decoder accepts a 256×256 logical texel atlas with a 128-byte row
stride; an original MAP02 subtexture UVWH of
`(240,192,15,15)` or `(240,208,15,15)` represents
**16×16 inclusive texels**. It checks the dimensions and source byte
bounds, preserves 16-bit CLUT words via `vh_ps1_clut4_read_raw`,
and produces RGBA32 texels using a caller-supplied pixel-format packer.
The Switch path supplies `RGBA8_MAXALPHA` through that callback
rather than assuming a host endian/order convention.

The native `source/main.c` fills those two UV regions with
asymmetrical **generated nibble indices**, supplies two synthetic
16-color palettes, and decodes both crops. The existing FT4
rasterizer then transfers the resulting pixels onto a normal and
mirrored four-corner screen-space quad in the diagnostic panel.

The new test `tests/test_ps1_indexed_texture.c` verifies:

- Even/odd 4-bit nibble order and row-stride addressing
- Exact little-endian raw CLUT selection and BGR555-to-RGB888 expansion
- Zero and STP-bit occurrence counters, without losing raw semantics
- Every expected output pixel after the CLUT-to-FT4 path, including
  padding and clipped canvas boundaries
- Invalid crop extents, short palettes, overflow-prone dimensions and
  invalid sampler arguments leaving output and statistics unchanged

Both `make test` and `make test-sanitize` include the test;
the MAP02 upstream workflow and host texture safety workflow independently
compile and execute it. The Switch toolchain workflow builds a new NRO
with both synthetic indexed4 panels.

**Important limitations:** source palette word zero can now
be *skipped* during FT4 rasterization, while STP is retained as a separate
per-pixel class. The normal Switch diagnostic shows zero-color cutouts
with STP copied unchanged; the mirrored diagnostic highlights STP pixels
in **magenta** through an explicitly labeled debug callback.
Magenta is **not** a PS1 ABR blend formula. This implementation does not
infer the correct blend mode, distinguish all textured GPU states, or
synthesize texture-page uploads, GPU ordering, GTE projection or polygon
shading. No original PS1 game assets are embedded.

The two FT4 triangles use a top-left edge ownership rule: each shared
edge pixel belongs to only one triangle. Without it, STP pixels along
the shared diagonal could be blended twice. Regression tests enforce
**exactly one STP callback per covered tagged texel**, no writes for
zero-color texels and unchanged destination row padding.

The source-level CLUT classification API is
`vh_ps1_decode_clut4_crop_classified` (optional byte-per-pixel class
mask: 0=transparent zero, 1=opaque, 2=STP). The old
`vh_ps1_decode_clut4_crop` stays source-compatible. The masked
rasterizer is `vh_canvas_draw_ft4_classified_rgba32`, with an optional
pixel-format-aware STP callback; `vh_canvas_draw_ft4_rgba32` retains
its original opaque default. This is a validated diagnostic path,
**not yet a pixel-equivalent simulation of original PS1 gameplay**.


## PS1 ABR reference blending and MAP02 ABE audit

A portable reference implementation of the four PS1 **ABR** blending
choices now lives in `source/ps1_abr_blend.h`. It reads the blend
mode from texture-page bits 5–6, and decodes the polygon semi-transparency
enable (**ABE**) from the real `POLY_FT4` GPU command byte:

| ABR | 5-bit channel arithmetic (B=old, F=new) |
| --- | --- |
| 0 | B/2 + F/2 |
| 1 | min(31, B + F) |
| 2 | max(0, B - F) |
| 3 | min(31, B + F/4) |

The reference uses **integer truncation** for halves/quarters, saturation
for addition/subtraction and bit replication to convert results back to
8-bit. The callback accepts a caller-specified packed pixel format via
RGB unpack/pack operations; `RGBA8_MAXALPHA` is used in the Switch
probe. This is a 5-bit reference implementation, not a verified
pixel-perfect model of PS1 dithering, modulation and framebuffer mask
behavior. Source: the PSX-SPX **GPU (MISC)** and **Rendering Attributes**
specifications.

Crucially, for textured polygons, a source texel is blended **only
when ABE is enabled in the polygon code and bit15/STP is set** for that
texel. Color `0x0000` is skipped. Nonzero unflagged texels are
copied opaque, and STP texels on polygons with ABE disabled are likewise
copied opaque.

The pinned US PC-port's terrain renderers (`RenderMapTile`,
`RenderEdgeMapTile`, `RenderOverheadMapTile`) all assign
`poly->code = GPU_CODE_POLY_FT4;`. The upstream enum defines
`GPU_CODE_POLY_FT4=0x2c` and `GPU_CODE_SEMI_TRANS=0x02`;
therefore **normal MAP02 terrain has ABE disabled**. The terrain
source audit asserts that none of the three render paths enables
semi-transparency, guarding against a false remastering change where
STP alone would trigger blending.

By contrast, the synthetic Switch demonstrator uses **0x2e**
(`FT4|ABE`) for its second panel, cycling through all four ABR
modes every 120 frames. The first panel tests transparent color-0
cutouts. Both use generated pixels instead of copyrighted game art.

The host tests `tests/test_ps1_abr_blend.c` exercise all four
formulas, clamping, invalid-state handling, ABE=off copying, GPU opcode
interpretation, the texture page bits, transparent-source clipping and
per-pixel STP blending through a real FT4. GitHub Actions tests these
with sanitizers and compiles the NRO.

Remaining work for original MAP02: feed validated source art, real
screen-projected vertices and ordering-table parameters. These ABR
diagnostics alone do not establish the visibility or visual accuracy
of any original map face.


## MAP02 side lighting and distance attenuation

The portable `source/map02_terrain_lighting.h` implements the
**terrain face-color rule**, reconstructed directly from the pinned US
PC-port `src/core/graphics.c`. This is a new stage between the
4-bit CLUT decoder and the textured FT4 rasterizer.

For normal and edge terrain, the source selects a precomputed
`gSideLightColor[tileModel->shades[faceIdx]]` entry (26 lighting
directions). It then calculates `fade = clamp(max(5,otz) - 150, 0, 256)`
and computes each GPU command color byte as
`side - ((side * fade) >> 8)` with integer arithmetic. The
overhead renderer does **not** use this distance formula; instead
it sets all three command channels to its supplied `brightness`
value. The source audit rejects changes to either contract.

The color is applied to already-decoded texture RGB using the reference
PS1 textured-polygon modulation rule
`min(255, (texel8 * command_color8) >> 7)`. The value **128** is
neutral, so a 5-bit texel expanded to RGB888 remains unchanged when
the side light is 128 and depth attenuation is zero. This CPU
approximation is deterministic and integer-only, but does not claim
pixel-perfect emulation of GPU rounding, original 15-bit framebuffer
quantization, color dithering, GTE projection or texture modulation
exceptions.

`vh_map02_tint_crop_rgba32` provides a stride-checked color pass
compatible with the existing CLUT4 decoded 16×16 texture crop.
**Transparent-zero/STP classes remain separate and unchanged**. Their
handling still belongs to the classified FT4 rasterizer, with the
primitive's actual ABE flag and ABR selection supplied explicitly.

The native Switch `source/main.c` diagnostic now demonstrates
a **synthetic** cycle of depths 150–406 for two independently tinted
indexed-4/CLUT texture crops. The first is opaque aside from zero-color
cutouts; the second illustrates the four ABE-gated ABR modes. Both
use generated texels and placeholder side-light RGB, not the game
disc's original textures or computed GTE lighting.

Validation:

- `tests/test_map02_terrain_lighting.c` checks the depth formula
  against an independently evaluated integer reference for all 256
  side-channel values across OTZ 0–899, plus boundary and saturation
  cases.
- The same test covers the full 26-entry light-index selection, the
  distinct overhead path, RGB modulation, invalid-stride refusal and
  shaded source pixels passed through FT4's transparency and ABR path.
- `tests/test_audit_map02_face_source.py` makes source regression
  tests fail on changed normal/edge face lighting or changed overhead
  brightness assignments.
- GitHub Actions and the host sanitizer suite compile and execute
  these tests; the Switch workflow builds and checks the NRO.

Outstanding work: read genuine MAP02 model normals and lighting
state, reproduce or approximate `UpdateLight` / GTE lighting for
the 26 directional entries, implement camera projection and ordering,
then compare the generated screen pixels with captured PlayStation
output. The verified **face-color arithmetic alone** does not complete
the lighting or game renderer.


## MAP02 26-direction face-normal classifier

The pinned US PC-port (`src/core/graphics.c` in
`14552fffa0e0b47e02b57592e274fc6e7a649923`) has two
related routines:

- `SetupLightNormals` creates 26 axis, diagonal and
  three-axis signed direction vectors, then normalizes them through
  `VectorNormalS`.
- `UpdateMapTileLighting` reads three vertices from a face,
  applies source-specific fallback indices for repeated corners,
  computes their cross product, then selects the candidate normal
  with the greatest dot product. Equal dot products use a six-term
  sign/equality tie-breaker before the chosen index is stored in
  `tileModel->shades[faceIdx]`.

The new portable `source/map02_face_direction.h` decodes the
raw **304-byte** little-endian `MapTileModel` face topology,
including the 22 8-byte vertices, 18 sets of face indices, and
`faceCt`. It reproduces the four repeated-vertex fallback branches,
calculates a **64-bit signed** cross product, and selects from the
original 26 direction signs. The selected lighting index is then
used to look up a caller-supplied `gSideLightColor`-equivalent
table, as implemented in
`source/map02_terrain_lighting.h`.

**Improved precision boundary:** the portable path now computes
mathematically truncated, normalized Q12 components for both the
cross product and all 26 candidate directions: **4096, 2896, 2364**
for one, two or three nonzero axes. An unsigned 128-bit integer
comparison calculates each quotient without floating-point rounding.
The original six-check tie-break now compares the actual normalized
Q12 values rather than only their signs.

This directly corrects a previous mistake: three-axis directions
used 2365, and comparing unnormalized cross products caused wrong
classification near diagonal boundaries. Ten previously incorrect
synthetic normals are pinned as regression fixtures in the C tests.

This is a *PC-port numerical reference*, not certified PS1 GTE
emulation. The pinned `platform/pc/src/libgte.c` version of
`VectorNormalS` uses floating-point sqrt and truncates to 16-bit,
whereas the portable version computes the exact mathematical Q12
quotient with integer arithmetic. The original `gte_OuterProduct0`
also loads one edge through signed 16-bit IR values before computing
its MAC outputs. Our portable full-width cross product does not yet
model every such overflow/rounding case; extreme or boundary-sensitive
geometry can still differ from PC-port or hardware behavior.

The synthetic native Switch probe now generates two local face
records, **+Y top** and **+X side**, calls the normal classifier
at startup and passes its indices to the side-light table. It
then runs distance attenuation, texture modulation, FT4 and
the earlier ABR demo. No copyrighted map models or artwork are
included in the NRO.

`tests/test_map02_face_direction.c` covers all **26** original
direction vectors as independently constructed synthetic faces,
the four degenerate-corner fallback cases, empty/out-of-bounds
face indices, collinear triangles, 16-bit signed vertex extremes
and unchanged caller outputs on invalid data. The host workflow
runs these with AddressSanitizer and UBSan, while the Switch
workflow compiles them and validates the NRO.

A new fail-closed source check,
`tools/audit_map02_direction_source.py`, parses the **actual pinned**
`SetupLightNormals` and `UpdateMapTileLighting` functions and compares
all 78 source component assignments against the 26 vectors compiled
into the portable Switch header. It also checks the original GTE
normalization calls, cross-product arguments, repeated-vertex
fallback branches, dot-product search and tie selection.
`tests/test_audit_map02_direction_source.py` deliberately mutates
the source and C array to verify that these changes are rejected.
The pinned-source audit is part of MAP02 GitHub Actions.

The new `--pc-libgte` option in
`tools/audit_map02_direction_source.py` verifies the exact pinned
`VectorNormalS` sqrt/truncation statements, the signed-16-bit
`PC_GTE_LoadOPV2` inputs, the `PC_GTE_OP0` cross-product equations,
and the new 4096/2896/2364 Q12 classifier. GitHub Actions
checks both pinned upstream Git blobs and enforces this contract,
without importing any copyrighted game data.

### Executed PC-port Q12 differential evidence

`tools/verify_map02_pc_normal_equivalence.py` extracts and compiles
the **actual** `VectorNormalS` function from the pinned public
`platform/pc/src/libgte.c`. On a synthetic deterministic corpus
of **2119 normals** (original axes, known formerly misclassified
boundaries, signed extremes and seeded random triples), the native
PC function and portable Switch integer reference returned matching
normalized Q12 components **and** identical 26-way lighting indices.
This check links libm for the original PC sqrt; the Switch runtime
continues using integer-only Q12 normalization.

The GitHub Actions source checker pins the original libgte Git blob,
compiles this reference under host GCC, and asserts the exact count
and successful comparisons. Failed or modified numerical source
anchors are covered by fail-closed Python regression tests.

**This result establishes numerical parity on the executed corpus
against the PC-port helper**. It does not prove behavior on every
possible normal, does not reproduce PS1 MIPS BIOS `VectorNormalS`
rounding, and does not simulate the GTE OP0 signed-IR truncation
for out-of-range edges. It is intentionally separate from real
MAP02 assets and captured hardware output.

The next fidelity milestone is an independently executed
GTE cross-product and signed-IR edge comparison on varied map
geometry, followed by the real 26-entry light-color table,
camera projection and captured gameplay comparison.


## MAP02 OP0 input register and MAC readback comparison

The separate `source/map02_op0_reference.h` models two intentionally
different paths for the terrain's `gte_OuterProduct0(first, second, result)`:

- **Pinned PC-port reference:** `PC_GTE_LoadOPV1` retains all 32 bits of
  the first edge; `PC_GTE_LoadOPV2` truncates the second edge to signed
  16-bit IR components. `PC_GTE_OP0` computes the cross product, then
  `PC_GTE_StoreLVNL` exports **MAC1–MAC3**, *not* saturated IR1–IR3.
  The portable model explicitly wraps the computed MAC into signed 32-bit
  output, corresponding to the native PC comparison compiled with
  `-fwrapv` (source-level signed overflow otherwise has undefined C
  behavior).
- **PS1 register-boundary approximation:** the pinned MIPS
  `gte_ldopv1` macro writes the first edge to the GTE matrix diagonal
  control registers, whose OP0 coefficient fields are signed 16-bit.
  The pinned `gte_ldopv2` writes the second edge to IR1–IR3; both
  inputs therefore pass through explicit 16-bit sign extension.
  The model returns the low 32 bits of the conceptual MAC results.

**Validated scope:** `tests/test_map02_op0_reference.c` covers the
expected signs, MAC-vs-IR distinction, extremes and output safety.
`tools/verify_map02_pc_op0_equivalence.py` extracts the actual
`Sat16`, `PC_GTE_LoadOPV1`, `PC_GTE_LoadOPV2`, `PC_GTE_OP0` and
`PC_GTE_StoreLVNL` functions from the pinned public
`platform/pc/src/libgte.c`, compiles them and compares MAC results
for 4106 deterministic edge pairs. The CI gate rejects changes to the
pinned source blob or these extraction/operation anchors.

**Not yet proven:** real GTE 44-bit accumulator overflow/FLAG behavior,
possible PS1 BIOS `VectorNormalS` differences, actual MAP02 face
classifications on disc geometry, or rendered pixels. The existing
`vh_map02_face_direction` is **not silently switched** to either OP0
model: it retains the separately tested full-width PC mathematical
normal reference until integration can be validated on actual maps.
The PS1 model is therefore only an independently testable input
boundary, not a hardware-exact emulator.


## MAP02 source-local OP0 geometry inventory (read-only)

`tools/audit_map02_op0_geometry.py` now provides a **local, resource-provenance
aware** face-by-face diagnostic for a user-owned `M_MAP02.PRS` or its
187264-byte decoded map. It uses the source-verified **616 x 304-byte**
tile layout (28-column backing storage, 24x12 active region), checks every
active tile's `faceCt <= 18` and valid 0..21 face vertex indices, and
uses the original `UpdateMapTileLighting` repeated-index branch order.
The C scanner compares three results **per face**:

1. Mathematical full-width 64-bit vertex-edge cross from the old
   diagnostic, retaining the historical reference classification;
2. Compiled-PC-compatible OP0 MAC model (32-bit first edge, signed-16
   second edge, wrapped 32-bit MAC readback);
3. PS1 input-register-boundary approximation (signed-16 first and second
   edges, low-32 MAC result).

All three are classified against the *same* previously audited 26-way
PC-port Q12 table. Counters distinguish edge-component truncations, MAC
mismatches, zero normals and classification mismatches. The report also
shows the two drawbridge faces `(z=8,x=19,face=0)` and
`(z=11,x=11,face=0)`, but never prints vertices or pixel data.

Run it from a checkout of the repository:

```sh
python3 -m tools.audit_map02_op0_geometry --prs '/owned/DATA/M_MAP02.PRS' --require-prior-provenance
# Or supply the privately decompressed source instead:
python3 -m tools.audit_map02_op0_geometry --decoded '/private/M_MAP02.decoded' --require-prior-provenance
```

The provenance gate accepts only the previously recorded decompressed
PRS SHA-256; a localized or otherwise different map must be studied
without that flag and reported as `matches_prior_prs_sha256=false`.
The scanner is compiled locally with GCC, accepts map bytes only through
standard input and returns aggregate JSON with source hashes. No original
asset is committed or written to disk. CI tests a **synthetic map only**,
including signed-16 OP0 divergence, degenerate/repeated faces,
rejected malformed records and strict provenance failure.

**Important scope limit:** Until a privately owned real-map buffer is
actually passed through this tool with matching provenance, CI demonstrates
correct interpretation of *synthetic* vertices only; it does NOT establish
whether MAP02's actual faces diverge. This is neither a PS1 hardware GTE
implementation nor proof of screen projection, draw order, runtime lighting
or rendered pixels. Existing Switch shading/runtime paths are untouched.


## MAP02 screen-space GTE projection and ordering reference

`source/map02_projection.h` implements a **pure, bounded diagnostic**
for normal terrain faces using caller-provided camera registers and local
16-bit SVECTOR vertices. The original pinned
`src/core/graphics.c:RenderMapTile` order is reconstructed exactly at
the command level:

1. `RTPT` projects the first three vertices and fills SXY/SZ FIFOs;
   `NCLIP` tests their signed `MAC0 > 0`. Faces with nonpositive
   `MAC0` do not submit a polygon or calculate AVSZ4.
2. An accepted face stores first three screen corners as FT4
   `x0, x1, x3`. The fourth vertex is projected through `RTPS`
   (which clears its own GTE FLAG) and stored in `x2`.
3. `AVSZ4` computes `OTZ` from the most recent four SZ entries using
   `ZSF4`; normal terrain clamps it to a minimum of 5 and inserts
   the primitive at `OT_SIZE - otz`. The diagnostic checks that
   this index lies inside the explicitly supplied OT length.
   The pinned renderer itself has no equivalent upper-bound guard.

The portable implementation uses the same UNR perspective divider table
formula (computed per call without mutable global state), Q12
rotation/translation, signed perspective multiplication, SX/SY saturation,
negative round-down arithmetic, NCLIP sign and 16-bit OTZ saturation as
the **pinned PC source**. It preserves separate RTPT and RTPS flags for
diagnosis; it does not emulate actual MIPS GTE timing, 44-bit accumulator
flags, BIOS routines, or GPU polygon rasterization.

`tools/verify_map02_pc_projection_equivalence.py` extracts and compiles
the **actual pinned PC** `Sat16`, `SatU16`, `BuildUnrTable`,
`CountLeadingZeroes16`, `UnrDivide`, `TransformOne`,
`PC_GTE_RTPS`, `PC_GTE_RTPT`, `PC_GTE_NCLIP`, and `PC_GTE_AVSZ4`
functions and compares the new model on **4099 deterministic synthetic
quads**. `tools/audit_map02_projection_source.py` independently
checks the original `RenderMapTile` culling, FT4 corner, AVSZ4 and
OT submission command order. Both gates reject changed pinned upstream
blob hashes or required function/renderer statement mutations.

**Evidence boundary:** the camera registers used in tests are
synthetic, not captured from real MAP02 gameplay. The actual Switch
renderer, GPU ordering table, runtime material data and artwork
were not modified. The result is PC-port mathematical equivalence
for these tested inputs, **not** live map pixels, real-camera placement,
full PS1 hardware equality, or evidence of a playable rendered scene.


## Capturing the *real* MAP02 camera and verifying projection (opt-in)

The synthetic GTE projection verification does **not** establish the runtime
view transform. `tools/instrument_map02_camera.py` now allows a
**read-only, opt-in** source-level camera trace from a separately owned
working PC-port checkout. It checks the exact pinned upstream Git blobs
for `src/core/graphics.c` and `platform/pc/src/libgte.c` before
producing two **new** `graphics.camera.c` and `libgte.camera.c` files;
it refuses to overwrite the original files or an existing output folder.

When these generated source units replace the corresponding translation
units in an independently built, locally runnable PC port, defining
`PC_FEAT` and `VH_TRACE_MAP02_CAMERA` exposes a temporary GTE
register accessor and a guarded normal-terrain trace:

- Restricts output to **map number 11**, `RenderMapTile`,
  face zero of `(z=8,x=19)` and `(z=11,x=11)`, with **one event per face**
  at its first normal-renderer visit with a non-null material.
- Captures 16 actual resident GTE control-register values **before**
  `RTPT`: nine RT matrix coefficients in row-major order,
  TRX/TRY/TRZ, OFX, OFY, H and ZSF4. These are **not inferred**
  from higher-level camera rotation or a screenshot.
- Captures four original 16-bit vertex positions, signed `NCLIP`
  MAC0, cull decision, and (when front-facing) the actual four
  `POLY_FT4` projected corners and **unclamped** `AVSZ4` OTZ.
  An NCLIP-culled face has null screen and OTZ in the trace.
- Emits JSONL `stage=camera_projection` locally. Trace output may
  contain copyrighted map vertices; **do not commit or upload the
  raw trace without deciding that it is appropriate**. The normal
  non-debug compilation excludes all added tracing symbols.

Command to generate the two compile-ready C translation units:

```sh
python3 -m tools.instrument_map02_camera /private/VandalHearts-PcPort \
    --output-dir /private/MAP02-camera-instrumented
```

The output is source-only; this is **not** a runnable build by itself.
Configure the pinned PC port's build to compile the generated
`graphics.camera.c` and `libgte.camera.c` **instead of** their
corresponding originals, and define `-DVH_TRACE_MAP02_CAMERA`.
Start the owned game and enter map 11 to obtain local JSONL records.

Then verify locally against the separately differential-tested
portable C GTE projection model:

```sh
python3 -m tools.verify_map02_camera_capture /private/camera-projection.jsonl
```

The verifier checks target IDs, types, bounds, unique first-only
events, signed NCLIP/visibility, screen corners and raw OTZ using
a compiled C projector. Its public JSON report contains only SHA-256
of the trace and aggregate counts (no map vertices or camera data).

**Caveats:** This instrumentation has been **compiled in CI against
the pinned public PC source**, but it has not been run in an actual
gameplay session here. The screenshot/visible pixels, correct tile
world-placement and actual PS1 BIOS/hardware accuracy remain
unverified. For a culled face the trace is taken at first observation;
it does not prove the face is always culled on later frames.


## MAP02 decoded terrain face → projected FT4 → indexed 4-bpp pixels

`source/map02_terrain_quad.h` joins several **already independently
tested** components into a runnable, portable **diagnostic** pipeline.
Unlike a static corner-order audit, it takes a decoded 304-byte tile
record and actually writes synthetic textured pixels into a caller-owned
RGBA32 framebuffer.

The new `vh_map02_prepare_terrain_quad` call:

- Accepts exactly **304 bytes** from a tile record matching pinned
  `MapTileModel`: **22** local `SVECTOR`s at 8 bytes each,
  `gfx[18]` at byte 176, `faces[18][4]` at byte 212,
  `shades[18]` at byte 284 and `faceCt` at byte 302.
- Preserves the source 16-bit material index and face shading index.
  `GFX_NULL=0` skips projection, including otherwise invalid vertices,
  as in the original normal terrain renderer.
- Decodes four little-endian signed 16-bit vertices via their validated
  face indices, then uses `vh_map02_project_face` to execute the
  **PC-port-matched** `RTPT/NCLIP/RTPS/AVSZ4` reference.
- Declares a quad drawable only when its face is accepted by
  `NCLIP > 0` and its depth fits the explicitly bounded ordering
  table. It prepares the original FT4 GPU corner mapping
  `face[0],face[1],face[3],face[2]` with caller-supplied UVWH.
- Rejects invalid record lengths, UV bounds, face count and vertex
  indices without mutating the output object.

The `vh_map02_draw_terrain_4bpp` call consumes a **supplied**
256×256 packed four-bit indexed atlas and 16-entry little-endian
BGR555 palette. It decodes the selected UVWH crop into caller-owned
scratch buffers, including the distinction between fully transparent
zero, opaque and STP-marked texels. It then rasterizes an affine
`POLY_FT4` through the already audited top-left pixel rule and
optional explicit STP blend callback. Nothing is allocated or saved;
the framebuffer and all scratch space belong to the caller.

**Asset-free execution test**:
`tests/test_map02_terrain_quad.c`, wired into both `make test` and
`make test-sanitize`, builds an invented 304-byte tile, identity-Q12
camera, packed 4-bpp test atlas, BGR555 CLUT and 56×48 framebuffer.
It checks all four projected FT4 corners, `NCLIP`, `OTZ`/OT slot,
every transparent source column, 16 STP blend callbacks, pixel
coordinates/stride guard, culled and out-of-OT faces, null material
and failure-without-output-mutation. The MAP02 upstream workflow runs
this same compiled integration test independently.

**Strict evidence limits:** The input vertices, camera, texture and
CLUT are synthetic. No game assets, authentic UV/material associations,
map-grid world transforms or original rendered pixels are certified.
The rasterizer is CPU-affine and **not** a PS1 GPU hardware emulator;
there is no live Switch gameplay renderer hookup or screenshot
validation yet. Authentic MAP02 material→UVWH, palette, camera and
placement still require the independent ongoing source/gameplay
provenance audits. Do not replace them with guessed values.

## MAP02 multi-face painter ordering via original PC GPU OT buckets

`source/map02_terrain_ot_scene.h` assembles multiple **prepared**
`VhMap02TerrainQuad` objects from the validated single-face pipeline
into a reusable caller-owned scene. The queue does not assign UVWH,
select an asset palette, guess GTE camera state or invent world
placement: each submitted face retains caller-supplied material data.

The pinned public PC-port `platform/pc/src/libgpu.c` establishes
the actual ordering-table chain:

- `ClearOTag` links buckets in **ascending array index**, 0 to
  `OT_SIZE-1`, beginning at `ot[0]`.
- `AddPrim` prepends a primitive to its bucket. Consequently two
  primitives at the **same depth bucket** render in the **reverse
  order they were submitted** (LIFO).
- Original terrain uses `OT_SIZE - max(5, AVSZ4 OTZ)` for its
  bucket. With ascending bucket traversal, **high-OTZ distant
  terrain is rendered before lower-OTZ foreground terrain**.

The new queue emulates these **bucket and link rules**, rather than
applying a generic ascending-OTZ sort. Both head and node arrays
are provided by the caller; submitting a quad is O(1) and never
allocates memory. Rendering first checks all referenced quads,
depths, bucket indices, links, texture buffers and available
scratch space, so malformed/cyclic chains are rejected before
touching a pixel. It then invokes the existing classified CLUT4
FT4 rasterizer with each primitive's supplied palette and optional
STP callback. Frame reset is explicit.

Source fidelity is independently gated by
`tools/audit_map02_ot_source.py`, which requires the **exact pinned
Git blob** for `libgpu.c` and checks all three
`ClearOTag/AddPrim/DrawOTag` ordering statements. Synthetic
`tests/test_map02_terrain_ot_scene.c` verifies three overlapping
polygons in deliberately scrambled submission order:
far green, then **same-bucket LIFO** blue and red, with red
winning the composited pixel. Other cases check capacity limits,
invalid/cyclic links, incorrect depth-slot associations, failure
without framebuffer modification, empty scenes and scene reuse.
Both `make test`, `make test-sanitize` and the pinned MAP02
upstream workflow run the regression.

**Accuracy limits:** This composits only terrain FT4 polygons;
the real game OT also contains sprites, environment commands,
translucent objects and other GPU primitives. The CPU rasterizer
is affine and approximate, not original PS1 hardware. The camera,
geometry, indexed pixels and palettes in these tests are invented.
Consequently a passing synthetic scene is **not proof** that the
authentic MAP02 renders on Switch. The real asset/UV/CLUT/camera
provenance stages remain independent blockers.


## Source-keyed external GTE screen/depth → terrain FT4 integration

`source/map02_external_gte_ft4.h` bridges **externally supplied,
independently established** GTE measurements into the existing
`VhMap02TerrainQuad` and source-authentic ordering-table compositor.
This deliberately bypasses the synthetic camera projection used by the
previous diagnostic. It **does not** reconstruct the real camera or
execute any GTE projection command.

The adapter accepts an owned, decoded MAP02 buffer of exactly
187264 bytes (616 × 304), plus one source-keyed observation per
accepted, externally observed terrain draw. Each observation must
explicitly include the source key `(z,x,record_index,face_index)`,
the matching face's signed GFX index and shade, **all four original
vertex indices and 12 local 16-bit coordinates**, four observed
screen XY pairs in **perimeter order**, raw GTE AVSZ4 OTZ, and a
caller-confirmed UVWH rectangle.

- The source key is anchored to the original 28-record physical stride
  (`record_index = z*28+x`), with active cells limited to 24×12
  and face indices limited to `faceCt` (maximum 18).
- Every vertex index, XYZ component, GFX and shade must match the
  exact corresponding decoded source record. Equal material numbers
  never excuse a mismatched source face.
- Each XY coordinate must lie inside the GTE saturated screen range
  -1024 through 1023. Raw OTZ must be an unsigned 16-bit value;
  `max(5,OTZ)` must address a bucket in the caller's OT.
- GPU corners are derived from **perimeter**
  `[face0,face1,face2,face3]` to **POLY_FT4**
  `[face0,face1,face3,face2]`, preserving the already
  verified `setUVWH` mapping.
- `vh_map02_prepare_external_batch` rejects duplicate
  `(record_index,face_index)` and validates **all** observations
  before writing any prepared output records. It leaves submission
  order unchanged for the caller to pass through
  `vh_map02_ot_scene_add`.
- A successful result sets `projection.visible=1` **only because
  the caller supplied an accepted submitted-face observation**.
  `projection.nclip_mac0`, SZ and RTPT flags are **not known**
  and remain zero. Never interpret them as genuine captured results.

The C integration test `tests/test_map02_external_gte_ft4.c` constructs
two imaginary 304-byte map cells in a complete synthetic 187264-byte
decoded buffer, with two distinct faces deliberately sharing the
same GFX. It associates three separate observations, checks source
key/vertex/GFX/shade binding, prepares FT4 primitives without computing
a camera, composites at two depths and tests the final pixel in
the original GPU ordering-table traversal and same-bucket LIFO
order. Mutation tests reject swapped face indices, mismatched
vertices, altered materials/shades, incorrect map strides, out-of-
range XY/OTZ, invalid UV, truncated decoded maps, duplicate
source face keys, and late invalid batch records without modifying
previous outputs. CI runs this under strict host and sanitizer builds.

**Evidence boundary:** the test source records, external observations,
texture pixels and palettes are **invented fixtures**. The adapter
cannot establish that caller-provided coordinates, UVWH, CLUT or OTZ
were genuinely captured in retail gameplay. No original game assets
are published; no live Switch gameplay renderer is connected here.
It performs a strict *consistency check plus diagnostic rendering*,
not a screenshot comparison or PS1 GPU hardware validation.


## Raw 1024×512 PS1 VRAM → genuine 4bpp tpage/CLUT/texture-window addressing

`source/map02_vram4_page.h` is the new **source-format texture bridge**
between a *caller-owned* original PC/PS1 GPU VRAM snapshot and the
previously tested source-keyed FT4 compositor. The entire input is
`1024×512×2 = 1048576` little-endian bytes of BGR555/STP halfwords.
The caller must independently supply the `tpage`, `clut` and GP0
texture-window register values **observed for that specific polygon**.
The adapter never guesses these values from material numbers or UVs.

For each local texel coordinate `u,v` in 0–255, the converter
recomputes PS1 texture-window addressing:

```text
u' = (u & ~(mask_x * 8)) | ((offset_x & mask_x) * 8)
v' = (v & ~(mask_y * 8)) | ((offset_y & mask_y) * 8)
word_x = (tpage & 15) * 64 + (u' / 4)
word_y = ((tpage >> 4) & 1) * 256 + v'
index = (vram[word_y][word_x] >> ((u' & 3) * 4)) & 15
clut_x = (clut & 63) * 16
clut_y = (clut >> 6) & 511
color_word = vram[clut_y][clut_x + index]
```

A successful call materializes a **full 256×256 packed 4-bit atlas**
(32768 bytes, 128-byte stride), plus the **16 exact BGR555 palette
entries** (32 bytes), suitable for
`vh_map02_ot_scene_add / vh_map02_ot_scene_draw`. It preserves index
zero, the CLUT raw transparency word and bit-15 STP; classification and
blending remain explicit policies of the existing CPU FT4 rasterizer.
The texture window is baked into the atlas, so FT4 UV coordinates
retain their unchanged original meaning.

Only 4-bpp tpages are accepted; 8-bpp and direct 15-bpp modes are
**explicitly rejected**, never misdecoded as 4-bpp. Malformed register
values, incomplete VRAM, undersized atlas and palette buffers fail
**without modifying any output**. Input/output memory must be
non-aliasing and owned by the caller.

The synthetic integration regression
`tests/test_map02_vram4_page.c` proves the complete chain:

**raw VRAM halfwords → texture window → 4-bit index → VRAM CLUT →
source-identity-checked MAP02 external GTE face → original OT bucket →
classified RGBA32 FT4 pixels**, with transparent index 0, opaque
palette entries and callback-mediated STP. It independently exercises
GP0 window mask/offset on both UV axes, unusual index positions,
storage guards and unsupported texture modes. Tests run in
`make test`, `make test-sanitize` and the MAP02 pinned-source CI.

To avoid accidentally matching a convenient approximation,
`tools/verify_map02_pc_vram4_equivalence.py` extracts the **original
public PC-port** `TPageOrigin` and `SampleTexture` functions from the
exact pinned `platform/pc/src/pc_raster.c` Git blob
`ba8a05d161ad778c0b75e452ff0a11ed163c65cd`, compiles
them with GCC, and checks the **actual BGR555 raw sampled halfword**
against the new atlas/CLUT output for **524288 synthetic pixel samples**
(8 varied tpage/CLUT/window register scenarios × 256²).
The MAP02 upstream workflow checks the original source Git blob and
runs this native differential as well as mutated-source rejection tests.
This proves tested agreement with the **PC implementation**, not
the PlayStation's hardware GPU.

**Evidence limitation:** these VRAM contents, camera observations,
UVWH metadata and polygon geometry are **synthetic fixtures**.
The adapter can consume a real owned VRAM snapshot, but does not
establish when or where it was captured, that source assets are
original, that the attached tpage/clut parameters correspond to the
same actual drawing frame, or that the CPU-affine rasterizer matches
hardware PS1 output. No proprietary VRAM snapshot is checked in.

## Multi-face single-frame GTE + VRAM4 preparation (explicit synchronization contract)

`source/map02_vram4_frame.h` now connects three previously separate
portable MAP02 components: source-keyed observed GTE FT4 geometry,
actual-format 4bpp VRAM page/CLUT extraction, and original PC GPU
ordering-table bucket traversal. Up to **32 caller-supplied visible
terrain faces** are prepared in one frame without heap allocation.

Every face carries **independent** observed tpage, CLUT, texture-window
mask/offset, four screen perimeter corners, original 12 local vertex
coordinates, source material/shade, UVWH, raw OTZ, and its original
`(z,x,record_index,face_index)` identity. Multiple faces can share
the same GFX while using different GPU registers and palettes. The
frame builder materializes a separate 32768-byte 4bpp atlas and 32-byte
CLUT for each face and queues its FT4 in original
`ClearOTag` / `AddPrim` traversal order (including equal-depth LIFO).
Resources remain caller-owned and immutable for the entire frame.

Crucially, the API requires `frame == vram_snapshot_frame` and also
requires **both** the observation and GPU-register frame labels of
every face to equal that identifier. All faces, unique source keys,
source-record vertex geometry, raw-depth bounds, 4-bit GPU register
modes and working buffer capacities are checked **before any caller
output changes**. A single malformed late observation or frame mismatch
leaves the output scene, texture pages and statistics untouched.

`tests/test_map02_vram4_frame.c` builds three entirely imaginary
terrain submissions: two faces of the *same* map cell with identical
GFX, but separate 4bpp page/CLUT state and equal OT depth, and a
farther third face with a third page/CLUT. It verifies the independently
selected palettes, STP callback count, FT4 pixel output, original OT
LIFO and rejected mixed-frame/bad-source/bad-register/undersized-storage
inputs without modifying output buffers. The strict host, sanitizer
and pinned MAP02 upstream workflows execute this regression.

**This enforces an input consistency contract, not proof of original
gameplay.** Numeric frame labels can be forged; a real atomic capture
still needs a trusted acquisition process and SHA-provenance of decoded
map, source trace and VRAM. Further, **one full VRAM snapshot is only
valid if the game does not alter the relevant texture/CLUT data between
polygon submissions.** If VRAM changes within a frame, the snapshot
must be associated with the appropriate submission event instead of
applying one frozen image to all faces. This diagnostic does not
implement GPU commands, character/sprite layers, true PS1 raster
accuracy, HD asset replacement or live NRO rendering.


## Local private MAP02 frame-bundle integrity gate

`tools/verify_map02_frame_bundle.py` accepts a **locally acquired,
caller-owned** decoded MAP02 buffer (187264 bytes), GPU VRAM image
(1048576 bytes), 1–32 submitted terrain face events and a SHA-256
manifest with frame labels. It validates exact source face identities
(including all local XYZ values), rejects reused keys or mixed frame
labels, compiles the portable PC-GTE reference to compare RTPT, NCLIP,
RTPS, FT4 screen corners and raw OTZ, and independently samples the
actual 4-bpp texture page/CLUT/texture-window bytes. Caller-supplied
original BGR555 pixel probes are checked when present, but never
inferred. The public JSON report contains **counts and hashes only**,
not geometry, raw VRAM, palette colors or camera data.

Full required local file layout, schema and CLI are documented in
`docs/MAP02_PRIVATE_FRAME_BUNDLE.md`. Asset-free mutation tests are
run by MAP02 CI. A successful report proves **self-consistency of
supplied files**, not genuine retail gameplay or PS1 hardware pixels;
GPU VRAM stability between submissions is not established by a
single snapshot, and the existing native Switch scene is unchanged.


## Source-keyed per-submission VRAM snapshots (offline timeline)

`tools/verify_map02_vram_timeline.py` extends the verified private
single-frame evidence gate to a **time-ordered sequence** of 1–32
original-GPU-polygon submissions. One independently SHA-256 checked,
full-size (1048576-byte) local VRAM snapshot is required **per event**.
Every event also has a consecutive submission index and an explicit
one-to-one VRAM snapshot index, as well as the same decoded source
face/GTE/UV/CLUT evidence already required by
`verify_map02_frame_bundle.py`.

Each event's own private snapshot is used for its entire indexed4
texture-window/CLUT sampling, PC-GTE reference check and recorded
BGR555 probes. The verifier also compares adjacent VRAM snapshots
word by word, reporting (aggregated only) all modified 16-bit words
and whether words **actually addressed by the next face's indexed4
texture and CLUT** changed. It distinguishes unrelated VRAM writes
from texture/palette mutations relevant to that face. Hashes and
counts are the only public results; source positions, pixel colors,
camera and raw user game data remain private.

The exact local file names, JSON schema and command are documented in
`docs/MAP02_VRAM_SUBMISSION_TIMELINE.md`. A dedicated eight-test
synthetic regression checks changed CLUT, changed texture source
word, unrelated VRAM writes, unchanged snapshots, SHA tampering,
symlinks, mixed frames, swapped event order and incorrect game
geometry/GTE/probes.

A snapshot timeline **does not establish uninterrupted GPU-write
monitoring**. An unobserved change followed by restoration is invisible
between adjacent captures, and the reported labels and hashes do not
prove original gameplay or the actual timing of a VRAM write. No
retail frame capture, physical PS1 GPU behavior or live Switch renderer
integration is claimed by these tests.


## Replaying original PC GPU VRAM transfers between source-keyed MAP02 submissions

`tools/verify_map02_gpu_write_ledger.py` adds a **strict, offline,
SHA-bound transfer ledger** over the existing private per-submission
VRAM timeline. Every event must be one of the source-backed
`LoadImage`, `MoveImage`, or `ClearImage` operations. In
particular, overlapping `MoveImage` executes the original
**row-major, in-place** copying order (not `memmove`). `LoadImage`
uses the original source rectangle stride and clipped VRAM writes.
`ClearImage` uses absolute VRAM coordinates and original
5-bit BGR555 truncation. The source audit locks the exact
`libgpu.c` and `pc_raster.c` public PC-port Git blobs.

Replaying begins with the first private full-size VRAM snapshot and
applies the time-ordered, separately hashed transfer stream. At every
submission boundary the result must **fully match** the next
independently hashed VRAM snapshot, not merely the sampled material
colors. Unexplained differences (including actual `POLY_FT4` raster
writes not encoded by this limited ledger) **fail closed**; they are
not silently classified as successful transfer events. The verifier
returns only aggregate counts and digests, never game pixels or
geometry. Nine synthetic tests cover clipped loads, color packing,
overlapping moves, tampering, missing commands, and unknown GPU
writes. CI also verifies the original pinned source anchors.

See `docs/MAP02_GPU_VRAM_WRITE_LEDGER.md` for private input file
format, SHA manifest, and local invocation. **This is still an
offline consistency gate**, not an authentic original-game GPU
command stream or continuous memory-write monitor. It does not
yet model `DrawOTag` raster writes, GPU state changes, hidden
intervening modifications or PS1 hardware behavior, and it does
not validate an actual MAP02 scene on Switch.


## Opt-in native PC GPU command-order and before/after VRAM capture

`tools/instrument_map02_gpu_native_events.py` generates a **separate,
read-only source copy** from the exact pinned public
`platform/pc/src/libgpu.c`. Compiling that copy with
`-DVH_MAP02_GPU_CAPTURE` introduces bounded snapshot hooks at the
actual `LoadImage/MoveImage/ClearImage` transfer executions and
around **each primitive processed by the native DrawOTag walker**,
including polygon, sprite, tile, and GPU draw-mode packets.
A capture requires both explicit private-directory and frame
environment variables; otherwise it performs no runtime output.
Non-instrumented compilation excludes the recorder symbol entirely.

`tools/verify_map02_native_gpu_capture.py` validates local
`before/after` event pairing, frame boundaries, each fixed-name
1-MiB native VRAM snapshot, FT4 metadata, and optional bounded
LoadImage payloads. It emits **SHA-256 and aggregate count only**,
including the number of VRAM words changed by native DrawOTag
versus transfer operations. Missing snapshots, invalid JSON,
wrong indices, symlinked files and incomplete pairs fail closed.
See `docs/MAP02_NATIVE_GPU_CAPTURE.md` for exact local setup
and privacy guidance.

CI source-checks and compiles the *actual pinned PC libgpu* with
and without the optional capture macro, and runs synthetic trace
integrity/mutation tests. CI does **not** execute retail gameplay
or supply an actual captured GPU frame. The recorder does **not**
capture each individual `PutPixel` call, cannot exclude
intervening write/revert events, and does not by itself join
polygons to source MAP02 face identities. Physical PS1 GPU
correctness, accurate screenshots and a live Switch gameplay
scene remain unverified.


## Strict two-clock MAP02 source face to native PC GPU FT4 join

`tools/verify_map02_source_native_ft4_join.py` now performs an
**opt-in, private, SHA-bound join** between an independently verified
decoded MAP02/GTE/CLUT evidence bundle and the separately verified
original PC GPU `DrawOTag` native VRAM/packet capture. A manifest
must explicitly identify the **game source frame** and the
**GPU DrawOTag frame**; the two counters are not assumed to be equal
or synchronized. Refer to `docs/MAP02_SOURCE_NATIVE_FT4_JOIN.md`
for the full local-file format and invocation.

Each source-keyed `(record_index, face_index)` normal terrain
face must match **exactly one** actual-format `POLY_FT4`
packet by all four GPU-order (0,1,3,2) screen corners, all four
UV corners, `tpage`, `CLUT` and GP0(E2) texture window.
Repeated or missing candidates, or one packet compatible with
multiple distinct source records, fail closed. The verifier
also checks every 16-bit VRAM word actually addressed by that
face's 4bpp texture and index-selected CLUT entries against
the captured *pre-draw* VRAM; unrelated render-target writes
are deliberately ignored. A capture that exhausted its bounded
64-record limit is rejected as potentially incomplete.

This join establishes **internal agreement between caller-supplied
records only**, not their historical provenance or a cryptographic
binding to original gameplay. It does not reconstruct GTE-to-GPU
timestamps, authenticate input sources, prove a complete GPU
frame, support fluctuating framewide texture bytes, or validate
physical PS1 raster output or live Nintendo Switch gameplay.
Regression tests use synthetic, self-contained input data only.


## Source AddPrim OTZ/LIFO → observed native DrawOTag ordering gate

`tools/verify_map02_source_native_ot_order.py` is a second offline,
privacy-preserving gate applied **after** the source-keyed
`verify_map02_source_native_ft4_join.py` accepts an exact geometry,
UV/tpage/CLUT/window and pre-draw VRAM correspondence. For every
verified submitted terrain face, the tool computes original PC-port
`ClearOTag/AddPrim/DrawOTag` traversal precedence:
`OT_SIZE - max(5, AVSZ4 OTZ)` buckets ascend; within each bucket,
`AddPrim` head insertion reverses caller submission order (LIFO).
The expected source-face subsequence must match the observed
corresponding FT4 subsequence in the captured GPU walk.

The input requires explicit, SHA-bound assertions that source events
were indeed captured in **AddPrim-call order** and belong with the
native events to **one ClearOTag/DrawOTag chain**. This tool cannot
authenticate those assertions. It tolerates unrelated intervening
GPU primitives and FT4s, but does not prove their relative order or
entire-frame GPU submission completeness. Screen AABB overlap counts
are **candidates only**, not pixel-level overdraw proofs. The result
contains aggregate counts and SHA values without source geometry,
camera positions or pixels. See `docs/MAP02_SOURCE_NATIVE_OT_ORDER.md`
for the private format and limits.

Asset-free regressions test same-depth LIFO, mixed bucket precedence,
interleaved native packets, tampered manifests, false frame labels,
ambiguous FT4 matching, and claimed ordering metadata. No retail
MAP02 gameplay, complete original GPU command stream, physical PS1
raster parity, or Switch running scene is established by these tests.
