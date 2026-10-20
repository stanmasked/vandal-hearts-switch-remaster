# MAP02 — pinned PC SampleTexture versus per-FT4 GPU state

This is a **source-arithmetic integration check**, not a capture of the
original PlayStation gameplay. It builds on the 32-case/2,097,152-texel
standalone VRAM4 comparison in Draft PR #317.

The existing three-face, asset-free C fixture
`tests/test_map02_vram4_frame.c` first builds a complete
`VhMap02Vram4FrameWorkspace` using the original
`vh_map02_vram4_frame_build` path. That path creates separate texture
atlases and palettes for each submitted POLY_FT4 and links each to its
ordering-table node. The frame contains three independently specified
pages/CLUTs and one nontrivial GP0(E2h) texture window; the existing
test also checks ordering-table insertion, STP blending and whole-frame
pixel output.

The new read-only differential tool compiles the actual
`TPageOrigin` and `SampleTexture` function bodies extracted from the
pinned public PC port (`HalmyLyseas/VandalHearts-PcPort`, commit
`14552fffa0e0b47e02b57592e274fc6e7a649923`, raster Git blob
`ba8a05d161ad778c0b75e452ff0a11ed163c65cd`). It then independently
checks the complete three *materialized per-face* 256×256 atlases and CLUTs:
**3 × 65,536 = 196,608 synthetic BGR555 texels per compiler**. It also
requires each ordering-table node to retain the correct per-face atlas,
palette, prepared quad and externally supplied UVWH.

Two negative controls deliberately violate the frozen-source contract
*after* frame construction: one swaps a face's CLUT identity, the other
removes the GP0(E2h) texture-window X mask. The unchanged compiled
PC-port reference must reject each case as a sample mismatch. This
prevents a false pass where the standalone page converter is correct
but a queued FT4 uses the wrong palette or texture-window registers.

CI compiles and runs the original frame test plus both negative controls
with GCC and Clang. The pinned public source is checked out directly
from its exact Git revision, and its blob hash is verified before source
extraction. The tool rewrites the C harness only in a temporary build
folder; the frame fixture, shipped source headers and private disc
contents are never modified.

## Evidence limit

All original frame, geometry, GPU register and VRAM inputs in this test
are deliberately synthetic. This does **not** attest the authenticity of
the original MAP02 from a user-owned PS1 BIN/CUE, prove that the proper
texture registers were observed from retail gameplay, establish GPU
semi-transparency or pixel-accurate rasterization, or demonstrate a
physical Switch runtime. The PC-port function is a source reference,
not an independently validated PS1 hardware implementation. Retain
the PR as Draft until both compiler jobs pass on its exact HEAD.
