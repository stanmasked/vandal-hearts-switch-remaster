# Map02 v58 — real PC-port OT ordering of GP0(E6) mask state (synthetic)

## Scope and boundaries

The pinned public PC-port
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`
uses *port-specific tokenized ordering-table primitives*, not raw PlayStation
DMA packets. v57 proved an explicit GP0(E6) adapter between `DrawOTag`
submissions, while v58 tests mask commands **inside a single real OT walk**.

`tools/apply_map02_gp0_ot_v58.py` applies an exact-anchor patch to the
disposable checkout AFTER the v57 mask-path patch, never upstream or `main`.
It creates:
- `DR_MASK` / `PC_GPU_PRIM_DR_MASK=6`, a synthetic PC-port-only OT
  primitive wrapping one unmodified literal `0xE6000000..3` command.
- `PC_SetDrawMaskPacket` for constructing that primitive.
- A case in original `DrawOTag` that consumes it in packet order using
  the v57 GP0(E6) decoder; invalid reserved bits do not change state.
- A trace-size case in the real `pc_gpu_trace.c` so the record path knows
  the complete command primitive layout, compiled in CI.

This is NOT proof of raw PlayStation GP0 packet parsing, a hardware DMA
decoder, or native PS1 binary patching.

## Executed-original GPU checks

`tests/map02_v58_ordered_mask.c` builds nine synthetic OT sequences with
interleaved GP0(E6) state packets and textured FT4 primitives in **one
`ClearOTag → AddPrim → DrawOTag`**. Cases include:
- set bit15, then protect an already marked destination;
- remove check, overwrite, then re-enable it on an unmasked destination;
- blend four ABR modes with source STP set;
- skip a transparent zero texel even when force-bit15 is active;
- reject an E6 word with nonzero reserved bits;
- preserve half-open drawing clip boundaries under mask protection.

The actual original `TrcPrim` callback sees every mask and quad packet
in the OT walk. The dedicated v58 link-time test shim records its walk order,
command words, UV addresses, semi bits and ABR modes; the independent Python
oracle refuses missing, duplicated, reordered, or changed packets.

The v58 interpreter computes **every native 48×48 and 2× 96×96
framebuffer halfword** independently, including masked destinations,
STP and all four ABR modes. An additional direct original-C `FillQuad`
pass must match every pixel of deferred 2× DrawOTag for the same ordered
primitive sequence. Real deferred HD worker configurations: 1, 2, 4.
64 synthetic filler packets enable the multi-worker branch.

Per compiler:
- 9 scenes × 3 worker configurations = **27 executed original-C scenes**;
- 9 × 3 × 2304 = **62,208 independently predicted native halfwords**;
- 9 × 3 × 9216 = **248,832 independently predicted HD halfwords**;
- 9 × 3 × 9216 = **248,832 exact direct/deferred C halfword comparisons**.

Inherited tests v45–v57 remain required. The added GCC+Clang workflow
compiles the original production trace serializer but does not perform
a full recorded-file replay on this milestone.

## Closed gates

- `retail_gp0_dma_packet_decoding_proven=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

No authentic map, game artwork, retail framebuffer, Switch runtime or HD
replacement file was used. A full original trace record/replay with E6
and actual retail command provenance is future work.

All changes reside in stacked draft PR based on v57. `main` is untouched.
