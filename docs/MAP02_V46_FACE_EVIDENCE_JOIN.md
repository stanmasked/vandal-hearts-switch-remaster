# MAP02 v46 — face-level PRS → game draw → OT / native and hi-res DDA

**Verified CI:** [GCC + Clang GitHub Actions run 38918146895](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38918146895).

## Important correction to earlier evidence

The v45 synthetic rendering test changed \`gMapRowPointers[8][19].gfx[0]\`
from 641 to 643 for frame 2 **after decompression**. Therefore the v45
histogram-based GFX-to-slot success **did not prove that the PRS face
(z,x,face) was the face being rendered on the second frame**.

v46 addresses that problem explicitly. Two different, fixed synthetic
map tiles are embedded into the compressed stream:

| PRS model location | Persistent game GFX | v24 local slot | tpage | CLUT | UV |
|---|---:|---:|---:|---:|---|
| z=8,x=19,face=0 | 641 | 241 | 5 | 31978 | 240,192 |
| z=11,x=11,face=0 | 643 | 243 | 5 | 31850 | 240,208 |

\`RenderMapTile\` reads each face directly from the original
\`ProcessMapFileData\` decoded grid and **never modifies its GFX**.
The source's existing diagnostic \`VH_Map02TraceDraw\` emits frame,
z,x,face,GFX,tpage,CLUT,UV and the renderer route.

## New strict verifier

\`tools/verify_map02_face_evidence_v46.py\` accepts three files from
**one** instrumented PC-port process:

- a PRS file, read with the v45 bounded decoder;
- game graphics stdout JSONL \`stage=draw\` events;
- GPU stderr v39 tagged-OT, v39 native DDA and v40 hi-res DDA events.

It checks, for every observed draw:

1. \`(z,x,face)\` exists inside exactly the decoded original-layout
   model, and the emitted GFX equals the **unmodified decompressed**
   \`gfx[face]\`, not just an aggregate histogram.
2. Local slot \`gfx - 400\` exists in the user-authored 120-entry v24
   table. Observed polygon tpage, CLUT and **UV origin** exactly match
   the v24 row. Unsupported/absent slots are refused.
3. A unique \`(frame,GFX,terrain-route)\` tagged OT primitive exists
   with the correct tpage and CLUT, and its token has actual sampled
   records in BOTH native and hi-res DDA passes.
4. No tagged OT record remains unclaimed. Duplicate draw records,
   ambiguous GPU candidates, wrong graphics frame counters, malformed
   GPU logs, orphan samples, corrupt palette metadata and missing
   deferred events all fail closed.

The source graphics frame counter and the GPU DrawOTag frame ID
are **different counters in the real game and may be offset**. For this
verification stage, the verifier deliberately demands exact equality
and refuses the evidence if they do not agree, rather than guessing
a synchronization offset. Future full-game tests may need a single
shared explicit frame identity inserted at draw submission.

The v46 verifier is conservative for repeated real GFX in one frame:
if multiple tagged OT primitives share the same frame, GFX and route,
it treats the mapping as ambiguous. Therefore it does **not** establish
whole-map fidelity or coverage. It also does not inspect every polygon;
the pinned \`VH_Map02TraceDraw\` instrumentation currently emits
\`stage=draw\` for first faces of only two watched locations
\`[8][19]\` and \`[11][11]\`. Extending safe full-map origin tracing
is a separate engineering task.

## Example usage

From the repository root with a single consistent source/session:

\`\`\`bash
python3 -m tools.verify_map02_face_evidence_v46 \
  /private/M_MAP02.PRS \
  /private/map02-graphics.jsonl \
  /private/map02-gpu-stderr.log \
  --output /private/map02-evidence-v46.json
\`\`\`

For synthetic data used *only* in the test, supply
\`--synthetic-fixture\`. That option is never a claim of retail
file authenticity.

Exit codes: \`0\` = unique, internally consistent sampled-face
evidence; \`1\` = malformed or contradictory evidence; \`2\` =
insufficient evidence.

**All results**, including synthetic successful joins, set these
report fields to false: \`retail_map_authenticity_proven\`,
\`genuine_gameplay_proven\`, \`full_map_texture_coverage_proven\`
and \`HD_replacement_approved\`. The tool cannot approve a
texture substitution, change rendering, modify PRS, or export model
vertices.

## Reproducibility and result

The workflow
\`.github/workflows/map02-v46-face-evidence.yml\` is stacked on v45.
It compiles and **executes** the pinned public original PRS decoder,
\`RenderMapTile\`, software GTE, actual OT walker and threaded DDA
using a synthetic full 28×12 model file. The bounded preflight and
native token-family differential tests remain enabled.

- v45 bounded preflight/adversarial tests: **34/34** per compiler.
- New face-correlation and negative cases: **21/21** per compiler.
- C decoder vs safe Python full 102,144-byte PRS: exact match.
- C decoder vs safe Python six token classes: exact match.
- Actual PRS face to game-produced UV/CLUT to GPU OT/native/hi-res:
  **two complete uniquely joined test faces**.
- Negative CLI scenario: manually wrong tpage in captured real
  synthetic-game graphics log is **refused**.
- Both GCC and Clang: **SUCCESS**.

The workflow publishes the test binary, synthetic PRS, graphics
stdout, GPU stderr, individual JSON reports and native hashes
as per-compiler artifacts.

## Remaining work

A truly user-owned **original** \`M_MAP02.PRS\` was not present or
tested; texture art is not bundled or injected. Next validation
needs a full real-map face trace that does not conflate identical
GFX, a shared frame/correlation ID for source and GPU events,
and genuine gameplay resources. This branch is a stacked draft,
not merged into \`main\`; this result is **not** a playable
Switch HD remake.
