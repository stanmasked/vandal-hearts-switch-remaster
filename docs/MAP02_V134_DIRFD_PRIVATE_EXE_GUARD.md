# MAP02 v134 — every parent directory opened without following symlinks

This stage extends the safe local-only user-owned original PS-X EXE MIPS GPU/DMA candidate audit from v131–v133. It stacks on [v133 PR #124](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/124).

## Safety problem and fix

Previously the reader used `O_NOFOLLOW` on the **final EXE file** but provided an ordinary pathname to `open`. A symlink in an **ancestor directory** could redirect the input to a different real file without violating the last-component no-follow check. The reader's strict `fstat`, 0600 owner, one-hardlink, size, PS-X header and two-pass identical-byte SHA-256 still applied, but the path itself had no no-symlink binding.

The new helper `_open_private_exe_dirfd` walks each parent component using `openat` through a chain of directory file descriptors. Every directory open uses `O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC`. The leaf uses `O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK|O_NOCTTY`. Path segments `.` and `..` are refused rather than normalized away; null bytes, empty paths and unavailable POSIX no-follow capability fail closed. Every intermediate descriptor is closed, including on failures.

The exact **file descriptor** returned by this guarded walk is passed to the existing two complete private reads and same-inode, metadata and SHA-256 checks. There is no second unguarded path open and no public file pathname, bytes or content hash.

## Regression checks

- Positive: original generated 10,240-byte synthetic MIPS EXE inside a nested private directory is opened and inspected by both analyzers.
- Negative: symlink on an ancestor directory, symlink on the EXE itself, embedded `.` / `..` traversal, missing leaf and wrong input type all refuse.
- Relative paths without traversal are supported from their original working directory; repeated reads may not leak directory descriptors.
- Production v131 and v132 CLI binaries refuse an ancestor symlink within a short timeout and do not disclose the supplied private pathname.
- Previous v133 FIFO no-writer refusal remains protected by `O_NONBLOCK` at the leaf.
- Independent GCC/Clang CI and the full pinned PCSX ReARMed GCC/Clang native workflow run the regressions. Five synthetic MIPS DMA2 / true VBlank/Unai scenarios and private SHA-256 evidence remain unchanged.

No original retail game file is placed in public CI. This improves safety for optional **local** analyses and does not prove the execution or identity of retail MAP02, original PS1 parity or Nintendo Switch HD parity.
