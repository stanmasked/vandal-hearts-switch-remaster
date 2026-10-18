# MAP02 v133 — fail closed on nonregular private PS-X EXE inputs

Stacked on [v132 Draft PR #123](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/123). The original read-only MIPS GPU/DMA candidate inventory remains private and does not execute original MAP02.

## Why the file type must be guarded at open time

The v131 scanner checked `fstat` and then refused any user-provided input that was not a private single-link regular file. But `open(path, O_RDONLY)` can **block before fstat** when `path` denotes a named pipe (FIFO) whose other end has no writer. A malformed local path could therefore stall the analyst before the regular-file checks.

The v133 fix adds `O_NONBLOCK` and `O_NOCTTY` while retaining `O_NOFOLLOW` and `O_CLOEXEC`. `O_NONBLOCK` prevents waiting at an empty FIFO open; `O_NOCTTY` prevents accidentally acquiring a controlling terminal through a character device. Linux ignores nonblocking mode for normal on-disk regular file reads. The original strict `fstat` tests, owner, mode 0600, hard-link count, EXE header/section bounds and two-pass SHA-256/metadata checks remain mandatory. No file is modified.

## Actual negative controls

A new independent test constructs a private 0600 FIFO with **no writer** and invokes the production `read_private_exe` in a separate Python interpreter with a three-second hard timeout. The only accepted result is an immediate `Refused`; a blocking open fails the test rather than hanging the whole CI workflow.

Both production CLI entrypoints (v131 and v132) independently refuse the FIFO within the same limit, with no private path or binary bytes in stdout/stderr. Owned directories and available character devices such as `/dev/null` are also refused.

The positive control builds exactly the synthetic 10,240-byte v129 PS-X EXE as a private 0600 regular file, reads it back through the protected two-pass path, and checks unchanged static GPU/DMA candidate counts on both the original and delay-slot-aware analyzers.

Separate GCC and Clang source workflows plus the pinned native GCC/Clang PCSX workflow run these regressions. The five real-VBlank GPU DMA synthetic tests and original private SHA-256 audit are unaffected.

No retail EXE is committed or uploaded to GitHub Actions. There is no claim of original retail MAP02 execution, physical PS1 equivalence or Switch HD parity.
