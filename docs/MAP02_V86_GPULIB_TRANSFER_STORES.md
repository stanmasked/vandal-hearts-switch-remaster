# MAP02 v86 — native gpulib GP0(A0) and GP0(80) VRAM store audit

v85 was green under both GCC and Clang (524,480 raster write attempts
in pinned synthetic Unai: 524,288 same-color, 192 changed-color).
v86 extends observability to the pinned **gpulib** VRAM transfer paths
which do *not* go through those Unai raster inner loops.

## Two explicitly different origins

1. **GP0(A0) upload:** 16-bit CPU→VRAM transfer emitted by the already
   authenticated, interpreted four-phase synthetic MIPS EXE. The opt-in
   probe observes the known synchronous `do_vram_line` stores (ordinary
   memcpy and masked `cpy_mask` variants), recording pre-store value and
   precisely the value the original path will assign. GPU→CPU GP0(C0)
   reads are excluded. Asynchronous GPU transfers are not covered.
2. **GP0(80) copy:** the existing signed MIPS EXE has *no* VRAM copy
   commands. After all four native emulator VBlank callbacks and the
   2,380-readback oracle succeed, the host issues two explicitly marked
   `GPU_writeDataMem` GPU copy commands: a 4×4 rectangle from
   (40,160) to untouched (256,160), then repeats the copy to exactly
   the same destination. The pinned original `do_vram_copy` executes
   and the host asserts real post-copy GPU VRAM readback equality.
   This **is not** a retail or interpreted-MIPS GP0(80) command.

For each path, two aggregate counters are recorded: logical
16-bit store assignments and same-value store assignments. The
simple memcpy and masked/overlap loop paths use the original upstream
logic without replacing gameplay output. A copy with identical source
and destination that `do_vram_copy_pre` skips will not count. These
are known synchronous gpulib destination-store paths, not a proof
of completeness across other emulator backends.

## Output and verification

The four new event kinds are:
`gpulib_a0_store_count`,
`gpulib_a0_same_count`,
`gpulib_copy_store_count`,
`gpulib_copy_same_count`.

They are appended to the existing shared native sequence immediately
before private journal export. The independent v86 auditor refuses
duplicates, missing events, overflow, asserted CPU timestamps,
nonconsecutive ordering, absent uploads or a host-copy count other
than exactly 32 assignments, 16 of which must be same-value.
This host-copy event sequence occurs *after* the last observed
emulator VBlank and must never be attributed to one of the four
executed MIPS phases.

The private journal retains byte-exact fsync/readback validation,
mode 0600, refusal to overwrite an existing result, no raw GPU event
artifact publication and no copyrighted game binaries.

The GCC/Clang workflow compiles pinned PCSX ReARMed revision
`8b6c163575e6ce9a0537553e0d4ed4225315955e` and executes all
earlier safeguards as well as the new copy postcheck. Before the
corresponding workflow passes, native v86 runtime is NOT verified.

## Out of scope

- Physical PS1 VBlank equivalence or timing.
- Authentic game/retail MAP02.
- Asynchronous GPU DMA, alternate GPU plugins, VRAM copies submitted
  by original game commands, or full pixel-write provenance.
- Whether all GPU paths have correct mask/STP/ABR behavior.

`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

This is a Draft-only diagnostic branch stacked on v85; main and
Switch production rendering are unchanged.
