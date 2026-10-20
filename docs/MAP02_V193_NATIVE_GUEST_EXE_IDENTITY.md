# MAP02 v193 — bind native guest PS-X EXE identity to ten PCSX executions

Prerequisite: MAP02 v192 Draft PR #226 passed all 85/85 GitHub Actions workflows on commit 95040170. The prior v192 verifier binds ten real subprocess exit codes (0 for clean mode 0, 86 for nine corrupted RAM modes) to the exact SHA-256 of each original PCSX stdout/stderr log, and proves 22 visual Unai GPU pass markers and 159 adversarial log mutations.

v193 also pins the input executable for those same ten native subprocesses. Immediately before and after every original PCSX invocation, the native job measures SHA-256 of the private generated V183_RAM_CORRECT.EXE. One per-process line containing the mode and two actual SHA-256 measurements is appended to a private-only ten-row receipt manifest. The manifest is never committed, printed, or uploaded. A read-only checker requires precisely ordered modes 0–9, compares all 20 recorded EXE hashes to the current original file fingerprint, and checks its descriptor-bound SHA-256 / inode / timestamps and the private manifest before and after the complete inherited v192 exit+log audit. It rejects missing, duplicated, reordered or forged receipts, symlink or oversized receipt manifests, symlinked executables, rewritten guest files, and changes during verification.

Required aggregate native marker:

VH193_NATIVE_GUEST_EXE_IDENTITY_PASS modes=10 guest_exe_hashes=20 exe_digest_unchanged=1 native_exit_receipts=10 log_hashes=10 original_retail=0

Independent GCC/Clang regression tests use an unmistakably synthetic PS-X EXE fixture and do not access private retail ROM bytes. This proof detects changed binary bytes at the immediately-before and immediately-after sampling points; it does not prove that privileged agents could never temporarily replace the EXE and restore it between reads, nor does it prove execution of the original retail game or a real Nintendo Switch console.

Full PR remains Draft until native GCC/Clang and inherited CI results are confirmed. Original private log bytes and EXE assets remain private.
