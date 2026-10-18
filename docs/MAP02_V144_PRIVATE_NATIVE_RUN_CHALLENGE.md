# MAP02 v144 — fresh run challenge for private interpreted MIPS receipts

Stacked on [v143 Draft PR #135](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/135), which passed **37/37** GitHub Actions workflows. The pinned real PCSX ReARMed interpreter produced an atomic, protected, `0600`, source-verified 19-event MMIO journal from the source-authored synthetic PS-X executable.

## New replay gap

The synthetic program produces the **same 19 tuples every run**. Even the complete, byte-checked receipt from v143 could be accidentally reused and mistaken for the latest emulator run. This is especially dangerous before attempting private retail research.

v144 requires an *independently generated, fresh 128-bit random hex challenge per emulator process*. It is created outside the output directory and never printed or uploaded. `VH144_RECEIPT_CHALLENGE_HEX` supplies the fresh 32-lowercase-hex-digit value to the **actual pinned native PCSX process**.

The native writer adds an exclusive private `0600` sidecar `vh144-run-challenge.hex`, opened within the already verified `0700` native receipt directory using `openat(O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC)`. It validates the fresh challenge, writes exactly 32 lowercase hex bytes plus one LF, and calls `fsync` **before** publishing the complete v143 event journal. The original atomic `linkat`/directory `fsync`, no-symlink ancestor checks, no-overwrite controls, bounded 19-event collector and emulated CPU/GPU/DMA/VBlank behavior remain unchanged.

A new independent local verifier `tools/check_map02_v144_run_challenge.py` opens all three private `0600` inputs with the existing descriptor-anchored, double-read safeguards: published native MMIO receipt, native challenge sidecar, and **separately retained external expected challenge**. It refuses mismatches, missing or malformed challenge, changed input, wrong permissions, symlinks, corrupted MMIO events and any attempt to equate valid input with a negative-control receipt. It additionally checks the entire canonical receipt's SHA-256 against an independent, byte-identical synthetic EXE/ELF construction. It emits only one aggregate PASS or REFUSED status, never the challenge itself, filesystem paths, hashes, individual PCs or GPU words.

The full GCC+Clang pinned native workflow keeps the original v129 five four-VBlank profiles and all v138–v143 checks. The two v142 positive/corrupt-receipt real PCSX processes now get **distinct fresh challenges**. The positive native trace must match its independently retained challenge and exact self-authored MIPS source; the corrupted native receipt must still refuse regardless of challenge. A third private verifier invocation deliberately compares the positive receipt against the other run's independent challenge and must refuse: this prevents accidental cross-run reuse even if both programs would otherwise emit identical event tuples.

Standalone GCC+Clang C11 bounds/UB sanitizer tests compile the same native challenge writer and check correct exclusive private publication, no-overwrite, malformed/missing challenge rejection, unsafe ancestor/symlink rejection and existing sidecar collision refusal.

**Limits:** A challenge matching a sidecar does not make the emulator producer cryptographically authenticated. A malicious local actor with access to *both* the writable receipt and challenge could forge a new pair; a nonce also does not prove the emulator binary's identity. Public workflows still run **only synthetic MIPS**, never the original retail `SLUS_004.47`. Authentic retail MAP02 instruction execution, physical PS1 parity and Nintendo Switch HD graphics parity remain unverified. Keep all original user-owned files out of public GitHub Actions.
