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
