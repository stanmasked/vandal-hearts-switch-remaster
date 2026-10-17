# MAP02 v88 — genuine gpulib async GP0(A0) DMA queue vs worker destination writes

Builds upon green v87 native pinned PCSX ReARMed GCC/Clang. This
stage adds instrumentation to the actual `USE_ASYNC_GPU` worker in
`plugins/gpulib/gpu_async.c`.

The existing synchronous observer cannot prove asynchronous queue
acceptance, execution or completion. The v88 code therefore records
four **independently derived** counters:

1. A0 transfer batches **accepted** by original `gpu_async_try_dma`.
2. A0 transfer batches **started** by the real `do_dma_write` worker.
3. A0 transfer batches **completed** after original worker
   `do_vram_line` calls and renderer cache update.
4. 16-bit destination stores, and the subset reassigning the
   previous 16-bit value, sampled in the worker *immediately before*
   original native writes.

Worker counters use GCC/Clang `__atomic` increment and acquire
loads. No v80 ring writes occur on the asynchronous DMA worker;
the frontend appends four sequential `async_dma_*` aggregates only
**after GPUfreeze has synchronized queued renderer operations**.

## Explicitly synthetic host control

All original signed MIPS phases, four real **emulator** VBlank edges,
2,380 VRAM baseline oracle reads, and v86/v87 synchronous
host-control cases run before this stage. The host then enables
`thread_rendering=1` through the actual PCSX callback, submits a
bounded batch of synthetic raster commands to keep the GPU worker
occupied, and sends 32 identical 8-pixel A0 transfers to an
initially zero VRAM location. Accepted queuing is *not assumed*:
the run **refuses** zero accepted commands, missing worker
completions, mismatch between worker logical store counts and
accepted pixel counts, no same-value assignments, or no new-value
assignments. Final VRAM is checked via original `GPUfreeze`.
The worker thread is disabled again before cleanup.

The 32 A0 commands and warm-up raster batch are **host-injected
tests**, not interpreted MIPS GPU commands, not original MAP02
graphics, and not physical PlayStation evidence.

## Limits

- Not all submitted A0 transfers necessarily use the asynchronous
  path; the original gpulib may take a synchronous fallback.
  The v88 counters reflect **accepted worker batches only**.
- Readback proves final pixel values, not exact wall-clock latency.
- The asynchronous GP0(80) copy path and GPU-to-CPU GP0(C0) read
  remain outside this specific observation.
- The worker path is tested inside pinned PCSX software graphics,
  not Nintendo Switch production or original game assets.
- Raw private JSONL never uploaded as CI artifacts. Event capacity,
  missing event refusal, exclusive publication and hash readback
  remain mandatory.

`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

This is an unmerged stacked Draft branch; production HD replacement
is intentionally still OFF.
