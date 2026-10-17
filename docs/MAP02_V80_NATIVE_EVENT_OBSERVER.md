# MAP02 v80 — bounded native GPU submission / emulator VBlank event observer

This first v80 increment is stacked on the v79 offline timeline gate.

An opt-in C recorder in the disposable, pinned PCSX ReARMed checkout registers three
types with a shared monotonic sequence, CPU cycle and a value:

1. `VH80_VBLANK`: from the already instrumented *original* `psxRcntUpdate`
   callback after `GPU_vBlank(1,0)`; `frame` is the emulator's `frame_counter`.
2. `VH80_GP1_MMIO`: GP1 control-register input observed from the original
   `psxHwWriteGpuSR` dispatch; `frame=0` is an **unknown frame placeholder**.
3. `VH80_GPU_DMA2`: DMA2 chain invocation input address, **not individual GP0
   words**; `frame=0` is also an unknown frame placeholder.

These records have bounded capacity (4096), overflow detection, explicit reset,
and strict source patch anchors. There is **no dynamic allocation, no GPU state
mutation, and no event-counter spoofing** by the observer. Overflow or invalid
event kinds increment the failure counter.

## What this does NOT prove

- No claim of an emitted, read-back, or validated runtime JSONL trace.
- No individual GP0 command consumption, completed rasterization or VRAM write
  observation; DMA2 address does not identify a particular GPU command.
- No asserted correspondence to real PlayStation electrical video timing,
  retail MAP02 scenes, native Switch rendering or HD readiness.

To reach true v80 native timeline evidence, integrate an opt-in runtime export
with exact readback, require `vh80_dropped()==0`, record start/stop identity
and source hash, verify genuine GP0 words from the GPU consumption path,
and revalidate each snapshot against actual recorded writes. Only after that
should v79's offline analyzer ingest an emulator-produced trace.

`original_retail_MAP02_verified=false` and
`HD_replacement_approved=false` remain mandatory.

The C observer has a dedicated synthetic unit test and a GCC/Clang workflow;
these are **not** substitutes for a full pinned PCSX build/runtime integration
test. Main and the actual HD renderer are unchanged.
