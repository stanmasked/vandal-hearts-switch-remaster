# MAP02 v55 — original DrawOTag, four distinct screen regions

Verified initial GCC + Clang success:
https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38937107075

Draft stacked PR: https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/34

## Purpose

Extend the successful v54 256-packet original GPU DrawOTag test beyond
a single overlapped rectangle. v55 spatially separates 24 six-burst
groups? No: the exact fixture has **24 total 8-command bursts**, split
into FOUR sets of SIX overdraw bursts, each in its own native screen
region. Each set contributes 48 significant GPU packets to a separate
OT depth bucket. A fifth OT bucket contains 64 nonoverlapping TILE
fillers, resulting in **256 real original DrawOTag packet visits per
synthetic scene**.

The original public PC-port source is pinned to:
HalmyLyseas/VandalHearts-PcPort revision
14552fffa0e0b47e02b57592e274fc6e7a649923.

Real original code called: ClearOTag, AddPrim, DrawOTag,
original libgpu.c and pc_raster.c, with the deferred threaded
supersampled 2x DDA. Production GPU files are NOT modified.

## Synthetic screen geometry and worker boundaries

| Region | Native x | Native y | Sample native | Sample 2x |
| --- | --- | --- | --- | --- |
| 0 | 80..95 | 48..71 | (88,60) | (177,120) |
| 1 | 144..159 | 108..131 | (152,120) | (305,240) |
| 2 | 80..95 | 168..191 | (88,180) | (177,360) |
| 3 | 144..159 | 204..227 | (152,216) | (305,432) |

Regions 0, 1 and 2 cross the actual four-worker clip-band
boundaries at native y=60, 120 and 180 respectively.
Every original FT4/SPRT/F4 source polygon is restricted to
one region, with persistent OT sorting across all five buckets.
Other prim classes include DR_MODE and TILE.

Each of the 24 8-command bursts includes actual DR_MODE,
indexed4 semi-transparent POLY_FT4, indexed8 STP SPRT,
semi-transparent untextured F4, direct15 STP POLY_FT4 and
an additional TILE. Only the first TILE in each region fills
that region's background, retaining the subsequent six-burst
STP/ABR history. The two synthetic scene variants reverse
the 4bpp-versus-15bpp FT4 source order and must yield
different final pixels in each of four regions.

The test-only TrcPrim stub receives callbacks from the
actual original DrawOTag walker. The independent validator
requires the exact 256 callback order, OT buckets, source
burst IDs, unique primitive types and frame boundary counts.
It explicitly distinguishes **24 SPRT** versus **48
terrain-shaped FT4** visits. These are synthetic polygons;
the identification is a primitive-type test, NOT proof
that any real retail MAP02 face was submitted.

## True 2x framebuffer and empty gaps

The native bounding rectangle spans x80..159, y48..227.
The actual HD bounding rectangle is therefore 160x360
= **57,600 BGR555 framebuffer halfwords**.

The C harness renders the same packet stream through original
DrawOTag, snapshots the full HD rectangle, resets it,
then draws identical semantic commands with the *original*
FillQuad/FillRect functions in explicit order. All 57,600
pixels are compared exactly, in addition to whole-surface
and independent per-region hash comparisons.

Three separate runs use VH_RASTER_THREADS=1,2,4;
the original code itself confirms the worker setting.
Two scenes times three configurations times 57,600 pixels
produce **345,600 actual HD halfword comparisons per compiler**.

Five independent untouched screen probe points must stay
BGR555 zero in native, DrawOTag HD and direct-HD output:
(120,60), (120,120), (120,180), (120,216), (88,140).
These are empty areas between synthetic polygons.
Any spill from a sprite or an incorrectly clipped terrain-
shaped polygon into these gaps fails the proof.

## Independent reference and regression

Files:
- tests/map02_v55_spatial_ot.c
- tools/verify_map02_spatial_ot_v55.py
- tests/test_map02_spatial_ot_v55.py
- .github/workflows/map02-v55-spatial-ot.yml

The v55 test reuses the **test-only** v54 trace shim.
Its verifier independently computes exact native and
2x STP/ABR BGR555 values for each of four regions,
reconstructs the OT walk without using actual C raster
functions and checks SPRT and FT4 as separate GPU classes.

Negative tests corrupt actual logged packet depths,
primitive types, color results, empty gap pixels or
full-surface hashes. All MUST fail closed.

Both GCC and Clang passed these **248 Python regressions
per compiler**, plus the full original executable pipeline:
34(v45) +21(v46) +21(v47) +25(v48) +28(v49)
+15(v50) +13(v51) +24(v52) +19(v53) +24(v54)
+24(v55) = **248 tests**.

The live original-GPU evidence and binary/object checksums
are uploaded as compiler-specific GitHub Actions artifacts.

## Strict boundaries

All MAP02-like geometry, palettes, texture words, sprites and
GPU display lists in this milestone are SYNTHETIC. Although
the original source code genuinely executes, no retail
M_MAP02.PRS, user-owned disc, authentic map gameplay capture,
real game screenshot or original VRAM/CLUT bytes have been
processed. This is not a playable Switch NRO and does not
enable any restored HD texture substitution.

Proof output always reports:
- retail_map_authenticity_proven = false
- genuine_gameplay_proven = false
- HD_replacement_approved = false

Code remains in unmerged draft PR #34 based on #32;
the default main branch was not modified.

## Next gate

Use the same independent fail-closed spatial proof to
validate synthetic triangle-edge clipping and mask-bit
interactions, then add a locally owned retail MAP02/VRAM
input path that emits only hashed/audited provenance
metadata rather than publishing original game data.
