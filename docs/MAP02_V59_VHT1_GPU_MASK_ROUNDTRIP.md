# Map02 v59 — real VHT1 GPU record/replay with ordered GP0(E6) masks

## What actually executes

The pinned original public PC-port
`HalmyLyseas/VandalHearts-PcPort@14552fffa0e0b47e02b57592e274fc6e7a649923`
is checked out in a disposable GitHub Actions directory and receives the
exact-anchor v57 pixel mask fix and the v58 **synthetic PC-port-only**
DR_MASK OT primitive. v59 adds one gated, observation-only patch to the
original `pc_gpu_trace.c`: when `VH_MAP02_V59_TRACE_FRAMES=1`, after each
actual replayed frame it prints byte-level whole native VRAM and 2× HD
framebuffer FNV64 hashes.

**The genuine original `TrcInit / TrcWrite / TrcPrim / TrcFrameEnd /
PC_GpuReplayTrace` implementations are compiled, linked and executed.**
They are NOT substituted by test-only trace stubs. Test shim functions are
limited to non-trace optional services such as presenting frames and disabled
HD-pack lookups.

## VHT1 capture and replay evidence

The test driver produces four wholly synthetic scenes and uploads both each
background and each 15bpp source texel via real `LoadImage`. It submits
`PutDrawEnv` and a tokenized OT with interleaved mask commands and textured
FT4 packets via `ClearOTag / AddPrim / DrawOTag`.

Original trace code writes the real `VHT1` format:
- `L`: exactly two real VRAM uploads per frame;
- `E`: drawing area with half-open clipping;
- `P`: state, GP0(E6) mask, and textured polygon packets in OT order;
- `Z`: real `TrcFrameEnd` frame delimiter.

The four frames cover mask-set then skip, successive mask enable/disable and
reopen, STP+ABR 2 and mask-on clipped edges. Exactly **11** literal E6 words
are traced inside original GPU `P` records. Each frame also submits 64
filler packets to enter the original multi-worker HD path.

A new process with fresh GPU state runs the **original**
`PC_GpuReplayTrace` on the captured file. It reconstructs OT primitives,
reexecutes original C rasterization and produces a full native VRAM and 2×
supersampled framebuffer hash after every frame. The independent Python
verifier checks exact VHT1 structure, source pixels, mask command words,
packet order, frame boundaries and both complete framebuffer hashes
against the original recording for 1, 2 and 4 deferred-worker
configurations.

Per compiler:
- 4 recorded frames plus 4 × 3 replays = 16 original-GPU frame executions;
- **12 whole-native VRAM byte-hash comparisons**;
- **12 whole-HD framebuffer byte-hash comparisons**;
- exactly 11 mask packets, 11 FT4 packets and 256 filler packets in the
  actual recorded VHT1 stream;
- changed recorded mask commands, source, clip, truncation and replay
  HD pixel hash are refused;
- inherited v45-v58 original-GPU/GTE/PRS/OT/2× regressions must still pass.

## What it does NOT prove

VHT1 is a custom original **PC-port tracing format**. Its DR_MASK
extension is NOT the retail PlayStation GP0 DMA format. This test does not
prove actual retail E6 command provenance, full GPU hardware timing, original
retail `M_MAP02.PRS`, an authentic PlayStation screenshot, Switch gameplay,
or replacement-HD textures.

Explicit gates remain:

- `genuine_retail_gpu_packets_proven=false`
- `original_retail_MAP02_verified=false`
- `HD_replacement_approved=false`

Changes remain in a **stacked draft PR based on v58**; `main` is
untouched. No original retail art, map file or proprietary assets are
uploaded into CI.
