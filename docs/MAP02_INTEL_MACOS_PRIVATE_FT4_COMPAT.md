# MAP02 — Intel Mac local verifier readiness

This child stage is stacked on Draft PR #330, whose unified, **synthetic**
source/GTE/VRAM/FT4 provenance tests already passed GCC and Clang on Linux.
The owner plans to use an Intel Mac for additional offline MAP02 checks.
Before asking the owner to connect any private drive, this branch tests the
actual combined Python/C checker under an x86-64 **macOS** CI environment.

## Coverage

The workflow uses GitHub-hosted `macos-15-intel` with both Python **3.9**
and **3.11**, Apple's native **Clang**, and an exactly pinned public
`pc_raster.c` reference. It checks:

- Actual `uname -s=Darwin` and `uname -m=x86_64` — no Apple Silicon
  substitution.
- Existing source/GTE/private-format timeline differential:
  **14/14 tests**, including two invented 1-MiB snapshots, 131,072
  synthetic 4-bpp source samples, a deliberately corrupted texture
  nibble, a post-verification snapshot rewrite and other negative cases.
- Existing combined PC-source + native FT4 GPU packet match:
  **25/25 tests**, including two different frame counters (411 vs 12),
  reversed GPU primitive order, late native/source file replacement,
  symlinks, explicit cross-clock binding and private-directory mode.
- Compilation and execution of the separate three-face native C11
  ordering-table / atlas / CLUT test using Apple Clang.

This exercises macOS filesystem semantics relevant to the offline verifier,
including `O_NOFOLLOW`, regular-file/no-link requirements, `pread`,
`fstat`, 0700 private directories and post-validation identity readback.
Only invented fixture bytes are present in Actions. Nothing from an original
PlayStation CD, Mac drive, user files or game capture is downloaded.

## Compatibility boundary

A green CI confirms this program on the **GitHub macOS 15 Intel runner**,
not macOS Catalina 10.15.7, every Intel Mac model, a user-specific clang
install, or local disk behavior. The real Intel Mac will still need an
individual offline check once it is available. The source-retail
provenance, GPU truthfulness and actual PS1 frame equivalence remain
unconfirmed regardless of a green synthetic test.

This branch does not touch game rendering or original data, and remains
a Draft stacked on #330; `main` must not be merged.
