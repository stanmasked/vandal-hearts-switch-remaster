# Map 02 v50 — actual original GPU DDA texture-depth and STP/ABR tests

**Confirmed successful CI:** [GitHub Actions run 38926035073](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38926035073) — both GCC and Clang.

## What has now been executed

This stage moves several v48/v49 independently modelled graphics branches
into an **executed test of the pinned public PC-port's real renderer**.
The test executable `tests/map02_v50_original_dda_modes.c` links
unmodified original `libgpu.c` and `pc_raster.c` from
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.

Each case constructs a small, controlled and **synthetic** BGR555 VRAM
image. It populates a 4bpp or 8bpp packed texture word and CLUT, or
a direct 15bpp word, configures `RenderCtx` and then calls the genuine:

`FillQuad → FillTriangleDDA → dda_span → SampleTexture → WritePixel`

The test does not substitute a fake GPU sampler or blend function.
It reads the resulting **real native framebuffer pixel** at a location
inside the quad. For every case it prints input texture metadata,
physical VRAM/CLUT addresses, source words, the original background
halfword and the actual resulting color.

The test is intentionally **separate from the terrain producer**:
the primitive's screen coordinates, UV and GPU state are controlled
synthetic inputs to `FillQuad`; this portion does not claim that a
retail map loader emits every tested graphics state. The inherited v49
CI separately continues to exercise the genuine game terrain producer,
software GTE, OT walker and native + threaded-hires DDA on the
synthetic full 28×12 grid with exact v24 texture mapping.

## Eighteen real raster scenarios

The executable directly exercises:

| Test family | Actual original GPU behavior |
|---|---|
| Indexed 4bpp opaque | packed nibble, CLUT, native pixel write |
| Indexed 4bpp zero texel | skip without changing background |
| Polygon ABE on but source STP clear | opaque write, no blend |
| Indexed 4bpp STP + ABR 0,1,2,3 | four native BGR555 5-bit blend modes |
| STP set with black foreground | nonzero source still blended |
| 4bpp with dithering | native 4×4 dither stage before 15-bit pack |
| Indexed 8bpp | low and high source byte plus CLUT |
| 8bpp source with STP | real CLUT STP and ABR path |
| Direct 15bpp | no palette access |
| Direct 15bpp with STP | native semi-transparent write |
| Direct 15bpp zero source | preserve background |
| GP0 window X/Y masks | remapped texture coordinate access |
| GP0 window offsets X/Y | remapped source-word selection |
| GP0 window over indexed 8bpp | 8bpp window path with STP |

These are 18 named, distinct test rows. **No retail texture pixels or
original PS1 disc content are bundled.**

## Independent reference, not a mock renderer

`tools/verify_map02_gpu_modes_v50.py` parses the actual executable
output and separately recomputes each expected result from:

- v49's Python oracle for GP0 window, texture-word address, packed
  4bpp nibble / 8bpp byte / direct15 and CLUT lookup;
- v48's Python oracle for BGR555 modulation, ordered dithering,
  source-zero skipping and the four STP-gated ABR formulas.

It compares its final expected BGR555 halfword against the **actual
post-FillQuad native VRAM halfword**. The CI rejects tampering with
an executed case's output, packed texture word, palette entry or
window mask/offset; it also requires the full set of cases, both zero
texel branches, and all ABR modes. Missing/inconsistent test cases
fail closed.

Usage when the repository's test binary and dependencies are built:

```bash
./proof/v50_real_native_gpu_modes > proof/SYNTHETIC_NATIVE_ORIGINAL_DDA_MODES_v50.txt
python3 -m tools.verify_map02_gpu_modes_v50 \
  proof/SYNTHETIC_NATIVE_ORIGINAL_DDA_MODES_v50.txt \
  --output proof/SYNTHETIC_NATIVE_ORIGINAL_DDA_PROOF_v50.json
```

The canonical automated reproduction is the workflow
`.github/workflows/map02-v50-original-dda-modes.yml`; it
checks out the pinned public upstream source and builds the
real C objects with GCC and Clang.

## Verified test results

| Regression suites | GCC | Clang |
|---|---:|---:|
| v45 bounded PRS decoder | 34 | 34 |
| v46 decoded source-face identity | 21 | 21 |
| v47 every-face OT token | 21 | 21 |
| v48 BGR555/STP pixel audit | 25 | 25 |
| v49 packed VRAM/CLUT oracle | 28 | 28 |
| v50 original native DDA mode oracle | 15 | 15 |
| **Total Python tests per compiler** | **144 PASS** | **144 PASS** |

Additional integration gates passed for **both** compilers:
- Real upstream PRS unpacker versus independent bounded Python decoder.
- Actual game `RenderMapTile`, PS1 software GTE, OT walking and GPU
  execution on synthetic model data.
- Source-word/CLUT and before/after-PutPixel checks on tagged terrain
  observations from the inherited v49 execution.
- Full native/hires framebuffer determinism under 1 vs 2 workers in
  the inherited synthetic terrain rendering scenario.
- **18 additional native real DDA mode scenarios** with independent
  output validation, including direct STP and ABR tests.
- Refusal of deliberately modified actual native output metadata.

CI artifacts `map02-v50-gcc-real-gpu-synthetic` and
`map02-v50-clang-real-gpu-synthetic` include
`v50_real_native_gpu_modes`, its logged 18 test outcomes,
the v50 JSON proof, earlier source/face/OT/pixel proof reports and
object-code checksums. GitHub may expire these artifacts.

## Explicit boundaries

The new 18-case mode matrix directly invokes **native** `FillQuad`.
It does **not** itself prove all corresponding graphics modes in
the deferred hi-res threaded target. That target is still tested with
the inherited opaque synthetic terrain test.

No authentic user-owned `M_MAP02.PRS`, game disc, original texture
palette, retail gameplay frame or actual HD-remastered artwork was
loaded or tested in this milestone. Successful synthetic GPU
arithmetic is not pixel-perfect proof for the complete original map.

No production GPU code or game data was changed. PR remains an
unmerged stacked draft, `main` unchanged, and every proof report
fixes `HD_replacement_approved=false`.

### Recommended next gate

Repeat the source texture/depth, transparent texel and ABR matrix
on the real deferred **hi-res target**, then build independently
captured synthetic VRAM snapshots and assess true map 02 assets
only when the user's legally held originals are available.
