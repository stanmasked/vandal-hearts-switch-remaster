# MAP02 v107 — original temporary-stage identity survives readback and linking

This Draft is stacked on the source recovery hardening in v106,
[PR #97](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/97).
The original pinned Unai/VBlank/VRAM diagnostics, canonical private JSONL
format and exclusive no-clobber naming policy remain unchanged.

## The stage-identity gap

The v82 publisher previously created `<final>.tmp` exclusively, wrote and
fsynced it, closed it, then reopened it by name to compare bytes and linked
the *named* stage into the final destination. An attacker with directory
write access could substitute a different inode at the stage name with
**identical contents**, defeating the byte comparison while changing
provenance. Pre-link cleanup could then delete the substituted file by
name despite claiming to unlink only the publisher's owned stage.

## New checks

- Capture the inode identity directly from the original exclusive
  `openat(...O_EXCL...)` descriptor, and its post-write metadata after
  the stage fd's fsync.
- Before and after exact-length readback, check that the named stage and
  reopened read fd still have the same original identity, size, 0600
  mode, single link and high-resolution metadata.
- Revalidate the original named inode just before hard-link publication.
  After linking, confirm the new final pathname points at the original
  inode; reject even if a substituted file had byte-identical contents.
- Before unlinking `.tmp` after hard-link publication, require that it
  still points at the original inode and has exactly two links. Refuse
  and preserve foreign names otherwise.
- If publication fails before linking, only attempt to clean a
  same-inode single-link owned stage. Never delete an observed foreign
  stage file. Final filenames are never reused or overwritten after
  an ambiguous post-link failure.

## Fault tests and limits

GCC/Clang compile the **actual** C publisher with an isolated
`VH100_FAULT_TEST` hook. Four deterministic same-byte stage inode swaps
are injected: after stage fsync, after complete readback, just before
`linkat`, and after final hard link but before `.tmp` unlink. The tests
must refuse in every phase and preserve foreign and owned relocated
inodes. Any linked final file remains in place after refusal, and a
fresh distinct name remains available for a new publication. A normal
build must not export the fault hook. v82/v98-v106 tests are rerun.

These snapshots do **not** provide an atomic defense against a fully
malicious actor racing between a final `fstatat` and `unlinkat` or
`linkat`; directory exclusivity remains required. No physical disk
power-interruption guarantee is claimed.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
`main` untouched. No private retail data or GPU traces are published.
