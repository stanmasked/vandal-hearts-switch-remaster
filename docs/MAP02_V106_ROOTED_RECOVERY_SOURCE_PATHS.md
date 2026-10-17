# MAP02 v106 — rooted recovery source paths and parent-redirection refusal

Stacked Draft after v105, [PR #96](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/96).
The v82 no-replace publisher and v103 intermediate path-component
symlink guard already protect **new** journal destinations. Prior v98
and v99 still opened/inspected **old** completed journals and abandoned
stages through ordinary absolute paths: `open(..., O_NOFOLLOW)` and
`lstat` only reject symlinks at the final component, not a symlinked
ancestor directory.

## Hardened recovery-only reads

- Use the pre-existing rooted `vh103_open_parent_safely` walk for
  old sources as well as newly published targets. No `.`, `..`,
  repeated separators or symlinked intermediate components.
- v98 reads the old 0600 journal with `openat` on an anchored old
  parent dirfd, validates both named inode and open fd against the
  pre-publication snapshot, and after publishing the fresh generation
  checks the old parent identity and the same old inode metadata.
- v99 state classification uses two `fstatat(AT_SYMLINK_NOFOLLOW)`
  checks on one anchored source directory fd; interrupted-recovery
  snapshots and revalidates the old `.tmp` through that same fd.
- New file publication is unchanged: O_EXCL stage, no-replace link,
  parent fsync, full double readback. A failure never deletes,
  overwrites, or reuses either old or fresh output.

## Native tests

Test-only native fault injection redirects the **old source parent**
during fresh publication (rename old directory + symlink to a decoy),
after source snapshot and before its final check. Both v98 and v99
must refuse, while the fresh committed file and original bytes under
the renamed old directory remain intact. Separately test symlinks in
immediate and deeper ancestor components, leaf symlinks, malformed
paths, and legitimate nested non-symlink paths. GCC and Clang rerun
v98-v106 native regressions.

No fault hooks are enabled in the ordinary pinned PCSX build. The new
code uses the existing test-only `vh102_test_parent_redirect` hook
solely for deterministic native tests.

## Limits

This closes the tested source-path symlink/parent-redirection gap, not
all conceivable hostile concurrent filesystem races. The private
directory must remain under exclusive control. No physical power-loss
or retail PlayStation test is implied. The v104 original pinned Unai
GPU/VBlank synthetic host evidence and private exporter remain
unchanged; no private journals, asset data or VRAM bytes enter public
CI artifacts.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
`main` untouched.
