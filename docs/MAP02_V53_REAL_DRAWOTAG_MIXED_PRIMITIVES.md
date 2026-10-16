# Map02 v53 — real DrawOTag mixed-primitive and GP0 state proof

Confirmed functional CI: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38932658792 — GCC and Clang SUCCESS.

## What was actually executed

Unlike v52, which called the genuine original GPU FillQuad directly, v53 uses the ORIGINAL pinned public PC-port ordering-table API:
ClearOTag → AddPrim → DrawOTag → native GPU walker → deferred 2x HD renderer.

Original source revision: HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923.

The 8 significant synthetic PsyQ packets are:
- DR_MODE: initially clear texture window.
- TILE: opaque solid RGB(40,64,88) background.
- POLY_FT4: opaque synthetic 4-bit indexed texture.
- DR_MODE: set 8bpp sprite tpage, ABR1, GP0 texture-window X/Y mask and offset.
- SPRT: semi-transparent 8bpp texture using the preceding DR_MODE and synthetic STP-green CLUT1.
- DR_MODE: clear texture window, set ABR3 for nontextured primitives.
- POLY_F4: untextured semi-transparent polygon taking ABR3 from current draw mode.
- POLY_FT4: direct 15-bit STP-red polygon using its own tpage ABR2.

64 additional nonoverlapping TILE packets force the genuine deferred hi-res renderer's worker path. Total: 72 packet submissions per scene. The significant packets use separate OT buckets and reversed AddPrim insertion so that the real token-bridge walker must preserve the correct order.

Two source-only synthetic scenes rearrange the opaque 4bpp and STP 15bpp FT4 stages. The original output MUST differ; this detects reordered or skipped primitives rather than just relying on equal-looking logs.

## Independent verification

The new Python program tools/verify_map02_actual_ot_v53.py computes BGR555 in the correct sequence, with opaque overwrite, palette STP, ABR1 on the sprite, ABR3 on the untextured F4, and ABR2 on the 15-bit FT4. The 8bpp sprite's source texture selection depends on the state set by DR_MODE.

The oracle independently verifies the source-only synthetic fixture's CLUT4, CLUT8, 8bpp texture page, texture-window metadata, packet counts and observed native/2x colors at (88,88) and (177,176). All inputs and commands are synthetic. The Python oracle does not call GPU color functions.

An additional ORIGINAL-C baseline uses the real FillQuad and FillRect functions directly with the same ordered commands and per-primitive texture state. After the real DrawOTag path, the test snapshots the entire 32x320 hi-res region. Every one of 10,240 framebuffer halfwords is compared exactly to the direct original-GPU baseline, with whole-region hashes as an additional check.

The same two scenes run in independent processes at VH_RASTER_THREADS=1,2,4. The CI checks the actual worker startup log, output consistency and exact whole-framebuffer regions.

2 scenes x 3 worker settings x 10,240 pixels = 61,440 exact comparisons per compiler.

Negative CI mutates actual output pixel, 8bpp CLUT, GP0 window flag and region fingerprint records. Each corrupted proof must fail closed.

## Reproduction

GitHub workflow: .github/workflows/map02-v53-real-drawotag.yml

CI builds tests/map02_v53_actual_ot_mixed.c alongside the original public PC-port GPU objects. It executes each worker configuration separately, then invokes:

    python3 -m remaster.tools.verify_map02_actual_ot_v53 \
      proof/SYNTHETIC_V53_ACTUAL_OT_1.log \
      proof/SYNTHETIC_V53_ACTUAL_OT_2.log \
      proof/SYNTHETIC_V53_ACTUAL_OT_4.log \
      --output proof/SYNTHETIC_V53_ACTUAL_OT_PROOF.json

CI proof artifacts contain the executable, C objects, stdout/stderr and JSON. No user game data is bundled.

## Verified test totals per compiler

v45: 34 tests
v46: 21 tests
v47: 21 tests
v48: 25 tests
v49: 28 tests
v50: 15 tests
v51: 13 tests
v52: 24 tests
v53: 19 tests
TOTAL: 200 Python tests per GCC and Clang, in addition to executable original source-code integration gates.

## Explicit boundaries

This is NOT the original retail M_MAP02.PRS, original game's texture/CLUT data or a captured retail gameplay frame. The exact mixed-packet inputs were authored as test fixtures for the original PC-port code, not extracted from the game.

The mixed-primitive DrawOTag proof does not imply whole-map fidelity, matching source screenshot pixels, a playable Switch NRO or HD texture replacement. Both the v53 and earlier diagnostic proofs keep HD_replacement_approved=false and genuine_gameplay_proven=false.

The next milestone can build bigger event manifests and test native/HD mixed primitive sequencing across multiple OT buckets and screen regions, then separately use user-authorized real map assets if available.

This is unmerged draft PR #30 stacked on v52 PR #27; main is unchanged.
