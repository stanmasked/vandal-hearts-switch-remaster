# MAP02 v103 — secure parent path components and final inode race checks

v102 successfully tested pinned PCSX ReARMed under GCC and Clang with
4,143 sequential private observer events, four emulator VBlank events,
2,380 synthetic MIPS VRAM samples, zero drops and 302,213 bytes in
the privately published JSONL. All v80–v102 checks were green.

## Remaining two directory / inode hazards

- v102 used an `O_NOFOLLOW` open of the **parent itself**, but a
  preceding intermediate directory name could still be a symlink.
- An independent v101 final verification might read a newly replaced
  inode holding **identical bytes** if the replacement happened
  between `fstatat` and `openat`, because earlier code did not
  preserve the pre-open pathname inode for comparison.

## v103 native protections

The original private publisher and reopened-file verifier now open
the requested absolute parent by starting at the filesystem root
and using `openat(dirfd, component, O_DIRECTORY|O_NOFOLLOW)` for
**every** path component. Dot/dotdot names, repeated or trailing
separators, oversized components and symlinks at any level fail
closed; the original directory-fd anchoring from v102 remains in
place. This is a POSIX-only private diagnostic path, not a generic
cross-platform path resolver.

Before opening the completed private file, v103 saves its original
`fstatat(..., AT_SYMLINK_NOFOLLOW)` device and inode. After
`openat`, it requires the opened descriptor to match that
**original inode**, in addition to the existing full byte readback,
post-read descriptor-versus-path identity check, file fsync and
reopened-parent directory fsync. Identical contents alone therefore
cannot hide an observed mid-verification inode replacement.

The original v82 exclusive file publisher still rejects occupied
paths, preserves existing private files, and refuses ambiguous
post-link states instead of attempting risky rollback.

## Deterministic adversarial tests

Only isolated native GCC/Clang tests compiled with
`VH100_FAULT_TEST` use the new
`vh103_test_replace_final(original,replacement,backup,phase)`:

1. Replace the published pathname with a **different inode holding
   identical bytes** between `fstatat` and `openat`.
2. Perform the same replacement **after the full byte read** but
   before the last metadata comparison.

Both must return refusal. Each test also verifies that old and new
data survive and neither filename is silently overwritten.

Additional native checks reject symlinked ancestor directories
and intermediate symlinks, allow a genuine multi-level directory,
reject unsafe leftover stages and leaf symlinks, and preserve the
original v101/v102 private security tests.

## Full pinned PCSX host-only smoke

After the original four emulator VBlank callbacks, 2,380 VRAM oracle
checks, actual pinned software Unai/GPU worker checks, and all v80–v102
diagnostics, v103 publishes and independently re-verifies two small
private-only marker files. It verifies at least 12 successful
component-safe parent traversals and four completed-file integrity
checks. It creates an **intermediate symlink** inside the private
directory that resolves back to that very directory; publication via
that symlink must nonetheless fail.

Three ordered bounded private-only aggregate events are checked by
an independent strict v103 auditor. The full original protected v82
private JSONL is subsequently published exactly once, checked for
byte-exact integrity and SHA-256, and is never uploaded to public CI.

**Scope:** test-controlled host input and synthetic MIPS oracle under
pinned PCSX ReARMed. Not retail Vandal Hearts MAP02, not physical PS1
GPU timing, not real power-loss/concurrent filesystem model checking,
and not Nintendo Switch HD rendering verification. The `main`
branch remains untouched.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
