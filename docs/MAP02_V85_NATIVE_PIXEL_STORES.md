# MAP02 v85 — native Unai pixel assignment instrumentation

This stage follows v84's successful pinned PCSX GCC+Clang emulated VBlank
and native 24-point VRAM value checks.

## Difference from v84

v84 sampled values *before and after* a GP0 handler but could not
distinguish a no-op from a real store that re-wrote the same 16-bit value.
v85 instruments the **destination store statements** in pinned Unai
software renderer (`gpu_inner.h`), including line, tile, sprite,
textured/untextured polygon paths, and the generic host-C++
GP0(02) clear fill path (`gpu_raster_image.h`, 32-bit stores counted as
two 16-bit pixels). The exact PIN and the 22 expected template sites
are checked fail-closed before source mutation.

Immediately before each real destination assignment, the injected
opt-in wrapper reads the pre-store value, compares it with the pending
value, increments the total 16-bit store attempts, and increments a
separate same-value-store count only when equal. It then performs
**exactly the original destination assignment**. Mask-rejected or
transparent skipped pixels never reach this wrapper and do not count.

For each observed renderer GP0 header, the same bounded event stream
contains consecutive records:
`gp0_unai_handled`,
`unai_sample_delta`,
`unai_store_count`,
`unai_same_store_count`.
The formatter refuses overflow-sentinel values, missing or incorrectly
ordered records, and same-value counts exceeding all observed stores.
The source observer refuses ring buffer drops and the private export
refuses replacing pre-existing results. The independent verifier
reports per-VBlank intervals with aggregate counts but **never shares
GPU payloads or per-pixel VRAM addresses**.

The GitHub Actions matrix builds pinned notaz/PCSX ReARMed with
GCC+Clang and executes the authenticated four-phase synthetic MIPS scene:
four actual *emulator* VBlank calls, 2,380 original native VRAM oracle
samples, post-Unai handler trace, 24-point v84 comparisons, and v85
instrumented native 16-bit assignment counters.

## Supported / unsupported claims

- `store_count>0`: a monitored C++ raster assignment was actually
  executed (including a same-value store).
- `same_store_count>0`: some assignment wrote the same value already
  present in the destination immediately before the store.
- `store_count==0`: **no store was observed at instrumented sites in
  that handler**. Do not claim no GPU memory write in general.
- The fast ARM assembly sprite paths, old Unai renderer, gpulib CPU→VRAM
  uploads, VRAM→VRAM copies, asynchronous GPU, and external plugin
  implementations remain outside this observer's complete coverage.
  They must not be silently counted as zero hardware activity.
- These numbers are about synthetic GPU paths in the emulated
  PlayStation, NOT retail Vandal Hearts MAP02 frames or a physical PS1.

`full_unai_dma_and_legacy_write_provenance_verified=false`
`physical_ps1_vblank_verified=false`
`original_retail_MAP02_verified=false`
`HD_replacement_approved=false`

No HD bypass is activated, and `main` stays unchanged.
