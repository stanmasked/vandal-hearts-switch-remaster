# MAP02 v92 — genuine pinned GPU asynchronous ring occupancy and DMA fallback

v91 passed both GCC and Clang in GitHub Actions with two verified
asynchronous→synchronous mode cycles and 3,940/4,096 bounded native
trace events. v92 adds **queue pressure** without multiplying the
per-GP0 timeline into an overflow.

## Native observation, not inferred VRAM snapshot counters

In pinned `notaz/pcsx_rearmed` at
`8b6c163575e6ce9a0537553e0d4ed4225315955e`,
the original `gpu_async_try_dma` can choose among three paths:

- Accept the entire GP0(A0) transfer into the real worker ring.
- Fall back synchronously if the ring is idle and completely empty.
- Fall back synchronously if available ring capacity is insufficient.

v92 instruments those original branch decisions **without changing
them**. It counts native attempts, acceptances, two mutually
exclusive bypass reasons, and the measured peak number of occupied
32-bit words. A post-`GPUfreeze` snapshot reads the real pending
number of GPU queue words; this must be zero.

The asynchronous A0 worker is independently counted by the existing
v88 original `do_dma_write` hook; synchronous fallback is counted
by the v86 observer on native `do_vram_line` writes. Both sides
distinguish actual changed-value versus same-value 16-bit assignments.
An enqueued-but-unfinished transfer is NOT classified as completed.
Queue-full bypasses may legitimately be zero on fast machines:
a zero value is NOT evidence of a queue overflow or exhaustion.
If there is no successful async admission at all, this opt-in test
fails because it cannot attest to the real worker path.

## Host-only native-pressure fixture

After the original signed four *emulator* VBlank callbacks, 2,380
MIPS synthetic oracle readbacks and all v86–v91 host controls,
the test starts the genuine software GPU thread and submits just
16 warm-up sprite commands (to limit the already dense journal).
It then submits 16 identical green GP0(A0) transfers,
each **256×32 16-bit pixels (4,096 data words)** to one
previously empty rectangular region of VRAM. This yields a known
**131,072 total logical 16-bit destination assignments**, no matter
whether the pinned native implementation accepts a command into the
asynchronous queue or falls back to a synchronized upload.

The native acceptance/worker/fallback counters must satisfy:

- `attempts=accepted+idle_fallback+capacity_fallback=16`.
- `0<accepted<=16`, `worker_completed=accepted`.
- `worker_stores=8192×accepted`;
  `sync_fallback_stores=8192×(16−accepted)`.
- `worker_same+sync_same=8192×15=122,880`.
  The initial upload changes 8,192 empty pixels; all remaining
  identical uploads reassign existing values.
- `4099<=observed_ring_peak_words<=32768` and
  `post_GPUfreeze_pending_queue_words=0`.
- The real `GPUfreeze` readback verifies each pixel of the entire
  original destination rectangle; it must equal the expected green.
  Then and only then does the host stop the actual GPU worker and
  append 11 aggregate native audit events to the private journal.

The pressure test **does not force a full queue**; whether full
capacity is actually reached is a measured outcome, not asserted
by the instrumentation. There is also no claim of hardware timing
parity, device-GPU DMA parity or starvation-free scheduling under
arbitrary workloads.

## Security and limitations

The regression parser refuses missing, duplicated, out-of-order
events; fabricated CPU or VBlank timestamps; impossible capacities;
uncompleted worker queues; bad worker/fallback pixel totals; or
incorrect same-value counts. All earlier v80–v91 private proofs
remain mandatory. The pinned native GCC/Clang CI compiles and
runs PCSX itself, verifies byte-exact journal readback and refuses
overwriting an existing diagnostic trace. Only aggregate summaries
are publishable: raw GPU words, pixel streams, authentic game assets
and private journals are never artifacts.

This is a **host-generated synthetic stress test** after the MIPS
oracle, not original retail MAP02 content and not a physical PS1
benchmark. `original_retail_MAP02_verified=false`,
`HD_replacement_approved=false`. The production Switch path and
`main` remain unchanged.
