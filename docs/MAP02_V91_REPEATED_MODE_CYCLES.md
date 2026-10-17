# MAP02 v91 — repeated GPU worker enable/stop and VRAM state retention

v91 builds on the verified pinned PCSX ReARMed software GPU v90. It
checks **two additional consecutive complete mode transitions**, rather
than treating a single async-to-sync handoff as comprehensive evidence.

## Design and origin of commands

The original signed MIPS four-phase synthetic scene and four actual
PCSX VBlank callbacks (2,380 readback checks) remain unmodified. v86
through v90 host-only GPU probes all finish before this v91 test begins.

Each v91 cycle uses a separate initially zero destination row in
synthetic VRAM, with only 32 warm-up sprites to keep the entire
historical v80 bounded event ring below its 4,096-entry limit:

1. Enable the real `USE_ASYNC_GPU` thread using the pinned upstream
   `plugin_call_rearmed_cbs()` callback.
2. Submit a GP0(A0) red upload, then a GP0(80) copy of those pixels,
   followed by E6=1, a green GP0(A0) upload and a masked GP0(80) copy.
3. Synchronize with original `GPUfreeze` and check source/destination
   colors, including the expected mask bit. Require **two real
   GPU-worker GP0(80) copies** (16 assignments, no same-value copies,
   one masked). Independently inspect accepted and completed A0
   worker transfers. The original PCSX gpulib can legitimately use a
   *synchronous A0 fallback* while threading is on; the v91 test
   records this rather than falsely labeling it a worker execution.
4. Flush and reset the GPU mask, shut down the asynchronous thread
   through the original pinned callback, then upload blue via native
   synchronous A0 and execute two identical synchronous GP0(80) copies.
   Read back the retained old async destinations and new sync
   destination, require 8 synchronous A0 writes, 16 synchronous copy
   stores and 8 repeated same-value copy assignments.

The second round uses a distinct VRAM row. A final readback checks
**both rounds together** after the second thread shutdown so that
no late operation may have corrupted results from the first transition.

## Strict observation

v91 appends two consecutive ordered groups of 11 aggregate events
(total 22), generated only by the main thread after both GPU workers
have stopped and independent readbacks have succeeded. The groups
contain accepted/completed/actual A0-worker stores, queued/completed
copy-worker commands, actual copy-store and same-value counts, masked
copies, and final synchronous A0/copy/same-value writes.

The independent verifier requires all 4 originally observed emulator
VBlank events, all predecessor v80–v90 audits, correct unique ordered
suffix, explicit unknown CPU-frame/cycle timestamps, no event drops,
no counter mismatch, and two equal native GPU-copy completion proofs.
A0 worker *acceptance may be zero* in a cycle when the pinned upstream
runs its documented synchronous fallback; completed worker transfers
must nevertheless exactly match actual accepted transfers.

The pinned GCC+Clang CI matrix compiles/runs the real software GPU
worker, verifies the private file is mode 0600, checks its byte-exact
readback and refuses duplicate publication. Raw private pixel data,
original game assets and command trace are not published.

This proves the checked synthetic transitions, **not** that the
unmodified retail game MAP02, physical PlayStation, other GPU plugins
or every possible interleaving behaves identically.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

No production Switch HD change and no modification to main.
