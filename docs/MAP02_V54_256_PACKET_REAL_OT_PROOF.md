# MAP02 v54 — 256-packet original DrawOTag walk and exact depth-bucket proof

**Executed original GPU C**: public, pinned PC-port at
HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923.

**Verified compiler matrix**: [GCC + Clang GitHub Actions success #38934791770](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38934791770).

## Why this stage matters

v53 tested eight significant mixed GPU packets and 64 TILE fillers
through the real ClearOTag/AddPrim/DrawOTag path. v54 expands this into
a long, repeated and genuinely ordered source stream while preserving
the original STP, ABR, texture-window and 2x threaded-raster requirements.

Two synthetic scenes each contain:

- **24 ordered bursts of eight significant packets** = **192
  overlapping semantic GPU packets**.
- The significant primitives are split among **four independently
  threaded OT depth buckets** (0, 1, 2, 3), six bursts per bucket,
  48 packets per bucket.
- **64 harmless TILE primitives** in OT bucket 7, required to test the
  genuine hi-res worker pool and complete OT list traversal.
- **256 actually submitted packets per frame**, not a paper model
  of submitted packets.
- Both ordering variants reuse source palette, geometry and GPU state
  but interchange the order of the synthetic FT4 packets; the final
  BGR555 colors differ.

The 8-packet burst includes the same genuine original code paths as
v53: DR_MODE state initialization, TILE background, indexed4 FT4 with
STP, DR_MODE switching to 8bpp/ABR1/GP0 texture window, semi-transparent
SPRT, another DR_MODE specifying ABR3, untextured semi-transparent F4,
and direct15 FT4 with STP and ABR2.

Only the **first** TILE paints the overlapping test area. Later TILE
primitives are sent to a distant region, while every 4bpp FT4 has
STP enabled, to ensure all 24 repeated bursts genuinely contribute to
the final image rather than a later opaque polygon obscuring all
earlier results.

## Crucial: what is observed rather than assumed

The test-only module tests/map02_v54_ot_trace_shims.c uses the public
PC-port's already existing trace callback hook **TrcPrim**.

At AddPrim submission, it registers an exact primitive **pointer** and
the source burst, logical slot and OT bucket. When the actual ORIGINAL
libgpu.c DrawOTag walker later calls TrcPrim, this test shim records
what the walker actually visited. The original production libgpu.c
is neither replaced nor rewritten.

The emitted trace has 256 per-frame real callbacks:

    V54WALK frame=N seq=N burst=N slot=N bucket=N filler=0|1 type=N

followed by the actual trace terminator:

    V54TRACE frame=N count=256 registered=256

The independent validator
tools/verify_map02_large_ot_v54.py demands exact alignment with
an independently calculated LIFO AddPrim / ordered depth-bucket
manifest:

- Frame 0 and 1 each has 256 distinct callbacks.
- Bursts 0..5 occupy bucket 0; 6..11 bucket 1;
  12..17 bucket 2; 18..23 bucket 3.
- Bucket 7 has 64 filler TILE packets in exact deterministic order.
- Every primitive type is stable across equivalent semantic packets;
  five distinct GPU primitive classes must actually be visited.
- Frame delimiters cannot be missing, duplicated or stale.
- Missing/extra/duplicated/incorrectly ordered elements **fail closed**.

The C fixture explicitly submits from the tail because the original
AddPrim inserts at the head of each OT bucket. The initial v54 CI
correctly exposed that submitting fillers in increasing order caused
them to appear in reverse order at the end of the actual traversal.
The test was corrected to submit fillers in reverse; **the independent
expected walk was not loosened**. Full v54 CI then succeeded.

## Real visual outcomes

An independent Python compositor executes all 24 synthetic
STP/ABR bursts using the original 5-bit BGR555 calculations, with
native coordinate (88,88) and true 2x sample coordinate (177,176).

The model predicts two observably different final native colors
for the two primitive-order variants. Their actual original C
DrawOTag native and deferred-hires pixels must match the
independent prediction.

An additional direct original-C FillQuad/FillRect baseline executes
the same semantically ordered 24 bursts, with original source texels,
CLUT, DR_MODE-equivalent state, transparency and ABR. The C test
snapshots **every halfword in the 32x320 2x framebuffer output
rectangle** and compares the real DrawOTag output byte-for-byte
against that direct baseline, plus FNV64 region fingerprint matching.

The two scenes run in separate processes at each of
VH_RASTER_THREADS=1,2,4, with the actual original GPU runtime
reporting real worker startup.

### Scope of comparisons per compiler

| Item | Observations |
|---|---:|
| Scenarios | 2 |
| OT packets per scene | 256 |
| Worker settings | 1, 2 and 4 |
| **Actual DrawOTag packet observations** | **1,536** |
| Actual overlapping semantic packets | 192/scene |
| Source 2x output pixels / scenario | 32x320 = 10,240 |
| **Exact hi-res halfword comparisons** | **61,440** |

A separate negative test mutates the original logged depth bucket,
OT slot, primitive type, BGR555 output and whole-region hash and
demands the independent verifier refuse each corrupted artifact.

## Regression totals

The CI extends the complete original source-code synthetic
integration pipeline used by v45 through v53, and passes:

| Suite | Tests/compiler |
|---|---:|
| v45 bounded synthetic PRS | 34 |
| v46 PRS source-face | 21 |
| v47 exact terrain face OT | 21 |
| v48 BGR555/STP/ABR per-pixel | 25 |
| v49 source VRAM/CLUT | 28 |
| v50 original native DDA modes | 15 |
| v51 original direct/deferred 2x DDA | 13 |
| v52 overlapping synthetic polygons and thread bands | 24 |
| v53 original mixed DrawOTag | 19 |
| v54 256-packet original OT and negative tests | 24 |
| **Total** | **224** |

Both GCC and Clang CI jobs completed successfully
in [run #38934791770](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38934791770).

Workflow: .github/workflows/map02-v54-large-ot.yml

The compiled C binary, shim, logs per 1/2/4 worker setting,
independent JSON proof and object checksums are in the uploaded
compiler-specific GitHub Actions artifacts.

## What is not claimed

- **No actual retail M_MAP02.PRS or original PS1 textures** were loaded.
- The original **code** was executed but all map geometry, CLUT
  pixels and test packets were deliberately synthetic.
- This is not an actual retail replayed gameplay frame; it does not
  establish a complete Nintendo Switch remaster, a retail map
  screenshot match, or tested HD texture replacement.
- The final artifact explicitly carries
  HD_replacement_approved=false and
  retail_map_authenticity_proven=false.

All changes remain in draft stacked PR #32, based on #30,
and are not merged into main.

## Suggested next test

Exercise a broader synthetic **spatially partitioned** OT set across
many regions and depth layers, combining terrain-tagged and untagged
sprites in the same clip band. A separate locally owned retail map
input is needed before claiming true gameplay/asset fidelity.
