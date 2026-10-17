# MAP02 v89 — real asynchronous GP0(80) VRAM copy, mask and sync-mode handoff

v88 pinned PCSX ReARMed `USE_ASYNC_GPU` GCC+Clang proved 32 accepted and
completed GP0(A0) asynchronous DMA writes, 256 worker pixel assignments,
248 same-value assignments and 8 changed-value assignments. v89 extends
the **worker** provenance to GP0(80) VRAM→VRAM copies and tests a clean
return to synchronous rendering. The signed synthetic original four-phase
MIPS / four real **emulator** VBlank / 2380 original readbacks are unchanged.

## Opt-in host control after earlier oracle

The test host enables the upstream real GPU worker after all prior
synthetic MIPS, v86/v87 gpulib and v88 worker A0 observations pass.
The only new GP0 traffic is HOST-SUBMITTED, not game/MIPS frames.

1. **Fast async copy**, source row 160 x=400..403 (green), destination
   row 360 x=720..723 initially zero. Repeat identical command.
2. **Masked async copy**, GP0(E6)=1 is submitted to the native GPU before
   two copies from the same source to row 360 x=730..733. Both writes must
   set the destination pixel mask bit (0x8000).
3. Native `GPUfreeze` synchronizes pending GPU work and asserts the
   actual eight destination pixels are exactly their expected colors.

The pinned `gpu_async_do_cmd_list` queue insertion site records only
successfully added GP0(80) commands. The native GPU worker records
command entry and return from the real `do_vram_copy` and tracks masked
copies separately. The original gpulib slow assignment and fast
`memcpy` copy paths are sampled **immediately before** original
destination stores: in-worker thread-local activity gates atomic total
and same-value 16-bit write counters.

The exact signed fixture checks four queued, four worker started/four
completed, sixteen 16-bit writes, eight same-value assignments, two
completed forced-mask copies, and correct GPU VRAM readback. The queue
alone is explicitly **not** sufficient evidence.

## Return to synchronous path

After restoring GP0(E6)=0, the test performs a full GPU worker
synchronization, disables `thread_rendering` through the real pinned
plugin callback, resets the v86 synchronous copy counters, copies the
already validated green row to a new initially zero four-pixel
destination and repeats once. The returned VRAM and counters must
show **eight synchronous 16-bit destination writes, four same-value**.
This is evidence of correct selected pinned software paths, not a
complete hardware-concurrency memory-model proof.

The raw private event stream gains seven post-worker **aggregate-only**
records. v89 fails on missing/dropped/forged or reordered events,
wrong native results, lost original oracle checks, or mutated private
files. Both GCC and Clang compile full pinned PCSX with `USE_ASYNC_GPU`.
No raw GPU words/VRAM content/retail assets are CI artifacts.

## Limits

- The injected copies are test-harness controls, **not** original retail
  MAP02 commands or physical PS1 operations.
- Async GP0(C0) readback and alternate GPU backends remain outside scope.
- The staged thread-local observer covers monitored original software
  GP0(80) destination stores, not necessarily every possible VRAM
  memory mutation on the original hardware.
- `original_retail_MAP02_verified=false`
- `physical_ps1_vblank_verified=false`
- `HD_replacement_approved=false`

No production Switch renderer change or merge into `main`.
