# Map 02 v51 — original GPU full 2× HD DDA and real deferred two-worker proof

**Milestone:** original unmodified PC-port `FillQuad → FillTriangleDDA → SampleTexture → PutPixel` now runs the same synthetic 18-case v50 mode matrix against **native VRAM**, **actual 2× hi-res framebuffer**, and the production **deferred hi-res display list with two raster workers**.

**Initial verified two-compiler run:** [GitHub Actions #38927677648](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38927677648). An additional later CI revision also compares complete rendered areas rather than just one pixel.

## Executed source and inputs

Pinned public upstream: `HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.

The standalone C harness at `tests/map02_v51_original_hires_modes.c` creates ONLY test-owned texture pixels and CLUTs in native software VRAM. For each of 18 cases it configures the original `RenderCtx` texture page, GP0 window, dither, ABE/STP and ABR settings, then invokes the original unmodified rasterizer:

- **Native:** `RenderCtx.target=0, scale=1`, with a known BGR555 background at the entire test quad.
- **2× direct:** `RenderCtx.target=1, scale=2`, `HiresEnsure()` and `HiresMirrorRect()` initialize the real hi-res memory. `FillQuad` draws the quad at twice the spatial resolution while looking up native texture data.
- **2× deferred:** after completely restoring the same hi-res background, `HiresFrameReset → HiresAppendQuad → HiresRasterizeThreaded(0,240)` processes the real deferred list using the same triangle vertices, GPU state, palette and original source VRAM. Sixty-four distant rectangles force the production `s_hprimCount >= 64` threshold so `VH_RASTER_THREADS=2` really uses the worker pool instead of the small-list single-thread shortcut.

There are **54 direct original-C DDA executions** over 18 distinct synthetic cases, plus 64 non-overlapping background fillers per deferred pass. No modified GPU sampler, temporary fake FillQuad or hand-coded approximate hi-res painter is linked.

## Independent reference and resolution distinction

`tools/verify_map02_hires_modes_v51.py` runs the v50 independent Python BGR555/packed-texel oracle separately on:

- 18 `V50` native records.
- 18 `V51HD` direct hi-res records.
- 18 `V51THREAD` deferred hi-res records.

It demands exactly the complete 18-case set for **each** pass, with no duplicates, and checks unchanged original source words, CLUT, texture-window metadata, transparency state and modulation.

The native reference sample uses coordinate **(88,88)**. Its corresponding hi-res sample deliberately uses **(177,176)**, not (176,176). Their BGR555 dither cells differ: (88,88) selects dither offset -4, while (177,176) selects 0. This verifies genuine per-hi-res-pixel dither calculations rather than accepting a nearest-neighbor enlargement of native VRAM.

The Python verifier computes each expected color independently with the correct **actual destination pixel coordinates**. It never asserts different-resolution pixels must equal each other.

## Full-rendered-area parity

In addition to the single independently verified per-case sample, the latest native C harness initializes the **entire** 16×16 original quad and mirrors it to a 32×32 hi-res background before each pass.

After the direct hi-res `FillQuad`, the harness snapshots all **1024** affected hi-res framebuffer halfwords. After the real deferred two-worker draw, it compares the same 1024 halfwords **one by one** and aborts on the first discrepancy. It also generates a separate FNV64 fingerprint for that complete region.

Across 18 distinct mode cases, the gate therefore tests **18,432 full-resolution framebuffer halfwords for exact direct-versus-threaded equality**. The Python report also insists on exactly 18 unique matching hash pairs and refuses missing or altered hash records.

This is stronger than matching only a center pixel or depending on a hash collision being improbable.

## What the executed mode matrix covers

Real native, direct 2× and deferred two-worker hi-res rasterizer execution for:

- Indexed 4-bit / indexed 8-bit / direct 15-bit source texture reads.
- Fully transparent zero texel skip and BGR555 preservation of background.
- Polygon ABE enabled with texture STP clear (still opaque).
- Source STP enabled and **all four ABR semi-transparency formulas**.
- STP-marked black texels and CLUT bit-15 transfer.
- Actual GP0 texture-window X/Y mask and offset behavior.
- Real ordered dithering on modulated texture pixels.

The GPU is the original pinned PC-port code. This is a **synthetic** test matrix, not retail game playback.

## Existing proof chain preserved

The v51 workflow is `.github/workflows/map02-v51-original-hires-dda.yml`. It retains prior independently executed synthetic map integration through the original PRS decompressor, `RenderMapTile`, software GTE, OT token attribution, native DDA, deferred hires renderer, v24 texture metadata, and bounded VRAM/CLUT source proof.

| Suite | Tests per compiler |
|---|---:|
| v45 bounded PRS | 34 |
| v46 face identity | 21 |
| v47 all-face OT | 21 |
| v48 BGR555/STP decision | 25 |
| v49 VRAM/CLUT lookup | 28 |
| v50 original native DDA mode matrix | 15 |
| v51 hi-res/multithread and adversarial verification | 13 |
| **Total Python tests per compiler** | **157** |

The original-GPU integration and separate corruption-refusal tests are **additional** to these Python unit regressions.

The CI deliberately corrupts actual logged HD pixel colors, deferred CLUT, full-area HD fingerprint and removes a mode to confirm a **fail-closed** result.

## Reproduce

From the repository's CI workspace after compiling the original GPU object files:

```bash
./proof/v51_real_native_hires_gpu_modes \
  > proof/SYNTHETIC_NATIVE_HIRES_DEFERRED_DDA_v51.txt \
  2> proof/SYNTHETIC_HIRES_DDA_v51.stderr

python3 -m remaster.tools.verify_map02_hires_modes_v51 \
  proof/SYNTHETIC_NATIVE_HIRES_DEFERRED_DDA_v51.txt \
  --output proof/SYNTHETIC_ORIGINAL_HIRES_DDA_PROOF_v51.json
```

The workflow checks for the explicit original rasterizer log
`[raster] hi-res worker threads: 2` and the expected 18 cases.

## Strict limitations

- All PRS models, CLUTs, GPU texture words and geometry in these tests are **synthetic**. No user-owned retail `M_MAP02.PRS`, PS1 disc texture, original gameplay session or full Switch NRO has been loaded.
- The 18-case matrix uses direct test-created quads; it does **not** prove that the real Map02 original scene emits every specialized GPU mode.
- The native/higher-resolution matching check compares **direct and deferred hi-res renderers**, which *must* produce the same hi-res pixels. It does **not** assert native versus hi-res images are pixel-identical, especially under different dither matrices.
- Original HD artwork is not generated, injected or approved. JSON keeps `HD_replacement_approved=false`, `genuine_gameplay_proven=false` and original full-map visual fidelity unproven.

Changes are in an unmerged **draft PR #24**, stacked on the v50 PR; `main` is unchanged.

### Next gate

Exercise these mode combinations with multiple stacked overlapping polygons, two vs several hi-res thread bands, and authentic per-frame texture-window changes through the original OT walker. On availability of properly owned retail resources, run bounded real-map validation before any opt-in HD texture substitution.
