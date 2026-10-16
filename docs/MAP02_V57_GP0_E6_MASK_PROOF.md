# MAP02 v57 — executed original GPU destination-mask GP0(E6) regression

## Why this is necessary

v56 demonstrated that the pristine pinned PC-port overwrote destination
BGR555 `0x8010` with opaque green `0x03e0`, because the software
`WritePixel` ignored the original PlayStation GP0(E6) *destination pixel
mask check*. This is a **negative original-port baseline**, not evidence of
PS1 hardware fidelity.

## What changed

The public pinned PC-port revision remains **unaltered in upstream GitHub**:
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`.
`tools/apply_map02_gpu_mask_v57.py` applies a small, exact-anchor change
only to the disposable `pcport` checkout used in CI. It fails closed
if the pinned source's pixel write / context / OT implementation changes.

The patched GPU function implements both GP0(E6) bits:
- bit 0: force destination BGR555 bit15 on pixels that actually write;
- bit 1: skip any rasterized pixel whose existing destination bit15 is set,
  *before* modulation/blending result is written.

Transparent texture index/texel zero still skips writing. STP and ABR 0/1/2/3
remain independent source-texture/blend decisions. Both native and deferred
HD passes receive the same mask state, *snapshotted per primitive in
`RenderCtx`*, and HD threads never race on shared mutable GPU mask globals.
Bulk VRAM fills/copies (`LoadImage`, `ClearImage`, `MoveImage`) remain outside
the polygon-drawing mask rule.

The adapter `PC_GpuGp0MaskE6(command)` accepts exact commands
`0xE6000000` through `0xE6000003` and rejects other opcodes or nonzero
reserved low bits without changing mask state. Mask state persists between
`DrawOTag` submissions. **It is not yet wired into an arbitrary retail GP0
packet-stream decoder**, because this PC-port does not expose one. The
new test explicitly exercises the adapter before real OT submission.

## Proof scope

`tests/map02_v57_gpu_mask.c` runs 15 distinct fully synthetic
FT4 scenes through real
`ClearOTag → AddPrim → DrawOTag → FillQuad → FillTriangleDDA → PutPixel`
in the pinned original GPU code plus the v57 mask patch.

Coverage includes: enabled/disabled destination checks on marked/unmarked
pixels; forced bit15 writes; check taking precedence over force; texel-zero
skip; STP and all four ABR modes; STP-clear opaque draw; half-open clipping;
and **two consecutive DrawOTag submissions with an E6 mask-state change**.
64 additional real OT primitives trigger the threaded 2× renderer when
configured. Native and true deferred 2× framebuffer results are independently
checked against Python oracle values from
`tools/verify_map02_gpu_mask_v57.py`, and the original direct HD
`FillQuad` is compared at every framebuffer halfword to real deferred
`DrawOTag`.

GCC and Clang each run 1/2/4 worker variants:
- 15 scenes × 3 workers = **45 actual original GPU case executions** per compiler.
- 15 × 3 × 2304 = **103,680 independently predicted native halfwords**.
- 15 × 3 × 9216 = **414,720 independently predicted 2× halfwords**.
- 15 × 3 × 9216 = **414,720 direct-vs-deferred original-C halfword comparisons**.

Synthetic independent full-surface FNV64 hashes and representative samples
reject altered mask source/state, geometry, clipping, STP/ABR, observed pixel
colors, and original GPU frame hashes. Adversarial mutations are mandatory.
The v57 workflow also retains the entire inherited v45–v56 executed-original
GPU/PRS/GTE/OT and unit-test matrix. The v56 destination-bit15 scenario
continues to characterize the *mask-disabled original baseline*.

## Gates still closed

- `GP0_E6_retail_command_integration_proven=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

No authentic `M_MAP02.PRS`, copyright-protected original game content,
Nintendo Switch game runtime, retail PS1 framebuffer capture or real HD
texture artwork is loaded. Additional real-game command provenance,
hardware comparison, and retail-asset validation remain prerequisites
before enabling HD replacement.

All work is in a **stacked draft PR based on v56**. Do not merge it into
`main` or claim Switch/remake completion until those independent gates
are passed.
