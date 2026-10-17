# MAP02 v105 — recoveries refuse changed original inode metadata

This draft is stacked on [v104](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/95).
The original no-replace 0600 publisher, parent dirfd safety, double full
post-fsync readback, synthetic pinned PCSX Unai GPU/VBlank observability and
independent private JSONL audits remain unchanged.

## The recovery-specific gap

v98 recoveries preserved the previous completed filename and checked its
device, inode, size, mode and links after a new observation was published.
v99 preserved an abandoned `.tmp` file similarly. A concurrent in-place
write could leave the same inode, link count and length, and those checks
alone would accept a modified old generation/stage.

v105 additionally compares `st_mtim` and `st_ctim`, including nanoseconds,
for the original old file descriptor against both its post-operation
descriptor and named path, or for the abandoned staged pathname before
and after fresh publication. Any observed mutation returns refusal.
The newly committed distinct filename is **not deleted, renamed, reused
or overwritten** on refusal, and the altered old file is also retained.

## Native deterministic regressions

The real C publisher is compiled under GCC and Clang with
`-std=c11 -Wall -Wextra -Werror` in both ordinary and test-only modes.
An isolated `VH100_FAULT_TEST` gate performs a real, synced one-byte
write with identical inode and file length immediately after fresh
publication, independently targeting:

1. The v98 previously committed 0600 journal.
2. The v99 abandoned 0600 `.tmp` stage.

Both must fail closed, retain the changed source, keep the separately
committed new file, and refuse reuse of the new final pathname.
Unmodified old sources and stages must continue to recover successfully.
The native-only mutation hook must be absent from the ordinary build.
Regression coverage for v98–v104 is rerun in the v105 matrix.

## Scope and limits

POSIX change timestamps detect these observed modifications but
**cannot guarantee detection of arbitrarily racing writers**, restored
timestamps, or collisions on coarse-resolution file systems. v105 is
not a byte-exact cryptographic guarantee for the old recovery input.
It assumes exclusive control of its private directory. No real power
interruption is simulated or claimed.

The evidence is still host-only synthetic instrumentation:
`original_retail_MAP02_verified=false`,
`physical_ps1_vblank_verified=false`,
`HD_replacement_approved=false`.
No retail binaries, raw GPU journals, or VRAM payloads are published.
`main` is untouched.
