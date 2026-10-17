# MAP02 v87 — native gpulib overlap, mask and VRAM X-wrap controls

v87 stacks on v86 (both GCC and Clang green) and adds three independent,
host-submitted GP0 test cases after the original four-VBlank, 2,380-sample
synthetic MIPS GPU oracle has succeeded.

## Three bounded controls

**Overlapping GPU copy GP0(80):**
The v86 host-controlled copy has already filled (256..259, 160..163) with
a uniform nonzero source. v87 copies it to (258..261, 160..163), where
two columns overlap and two columns are initially zero. The native
`do_vram_copy` slow path uses its staging buffer before assigning
destination pixels. A real `GPU_freeze` readback must reproduce the
pre-copy source exactly: **16 logical assignments, 8 same-value**.

**Masking GP0(A0):**
The host first uses GP0(E6)=1 to write four red 16-bit values with bit
15 set to initially clear (400..403,160). It then sets GP0(E6)=2 and
uploads four green values to the same pixels. The original
`cpy_mask` path preserves the masked destination's old values, while
its C implementation still executes four identical-value destination
assignments. Finally GP0(E6)=0 allows replacement with unmasked green.
Real VRAM readback is required after every stage:
**12 logical assignments, 4 same-value**. This validates the pinned
emulator implementation, not electrical PlayStation mask equivalence.

**X-wrap GPU copy GP0(80):**
Four source pixels from (256..259,160) are copied to (1022,1023,0,1)
on row 160 with native modulo-1024 addressing. Repeating the same copy
tests previous-value writes. The original slow copy path is invoked and
the result checked by GPU readback:
**8 logical assignments, 4 same-value**.

## Evidence integrity and provenance

- All v87 GPU commands are **host-originated diagnostic controls**, not
  original game commands, and not interpreted MIPS instructions. They
  execute only after the original four VBlank edges and v86 host-copy
  controls. The original synthetic MIPS A0 upload remains separately
  accounted for in v86.
- The existing bounded native event buffer gains six aggregate event kinds,
  each with unknown CPU cycle/frame placeholders `0`. They are emitted
  after the three controls and the retained v86 aggregate group.
- The v87 verifier checks event sequence continuity and unique ordered
  suffix, exact counts (16/8, 12/4, 8/4), no fabricated frame/CPU time,
  original VBlank presence, and the previous v86 baseline.
- The pinned PCSX ReARMed GCC/Clang full-build workflow runs source
  patching, independent unit regressions, the actual emulated GPU,
  2,380 original MIPS-oracle readbacks, and private mode-0600 exclusive
  atomic-like journal publication with byte-for-byte readback.
  CI uploads only status summaries, never raw GPU commands, pixels,
  copyrighted assets, or the trace.

This extension deliberately does not claim coverage of all DMA,
asynchronous backends, the physical PS1, or retail MAP02.

`original_retail_MAP02_verified=false`
`playstation_hardware_mask_equivalence_proven=false`
`HD_replacement_approved=false`

`main` and production Switch HD rendering remain untouched.
