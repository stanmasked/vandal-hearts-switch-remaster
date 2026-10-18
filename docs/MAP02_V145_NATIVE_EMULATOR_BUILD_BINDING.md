# MAP02 v145 — pinned native emulator ELF identity bound to actual MIPS receipt

Stacked on [v144 Draft PR #136](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/136), confirmed **38/38 GitHub Actions successful**. The pinned GCC/Clang PCSX ReARMed interpreter executed **only a source-authored synthetic** PS-X executable, observed 19 GPU/DMA `SW` events and stored private ordered event receipts with atomic publication, independent random per-run challenges and exact EXE/ELF source verification.

## Remaining identity ambiguity

The v144 run challenge detects accidental reuse of *another run's* journal, but does not identify which host emulator ELF was launched. Two different host executables could produce identical event records, making the claimed runtime source ambiguous.

The new **two-phase** `tools/check_map02_v145_native_build_binding.py` introduces a private build identity manifest. **PREPARE**, before native execution:

- Opens the actual host PCSX ELF using no-symlink **all-component** descriptor traversal; requires an owned regular executable, one link, no group/world write permission, maximum 64 MiB.
- Reads the *whole host executable twice* from the same descriptor and checks unchanged inode metadata and SHA-256.
- Independently regenerates the source-authored v129 synthetic PS-X executable and records its SHA-256. Checks the source snapshot's pinned PCSX repository commit constant `8b6c163575e6ce9a0537553e0d4ed4225315955e`; native GitHub CI also independently checks `git rev-parse HEAD` against this pin before and after running.
- Checks the already generated externally retained **0600** v144 run challenge, storing its SHA-256.
- Writes these identities as canonical JSON to a newly created **0600** manifest within a `0700` controlled private directory, using owner-verified dirfd, `O_CREAT|O_EXCL|O_NOFOLLOW` and `fsync`. Existing manifests never overwrite; partial own files are removed on failure. No build hash or private source bytes are printed or uploaded.

After the genuine native interpreter runs, **VERIFY** repeats full ELF binary double-reading and SHA-256, source-generated EXE digest and independent challenge reads against the pre-run manifest, and independently runs v144's complete event/EXE/ELF source-matching verifier. It reopens the binary and all protected manifest/challenge inputs after verification to detect mutation. A different binary, modified ELF, changed challenge, altered 19-event journal, untrusted path, mode/owner, malformed manifest, replayed receipt or inconsistent pinned upstream SHA-1 commit is refused.

### Native workflow

The pinned GCC+Clang native workflow runs PREPARE **separately for positive and deliberately corrupted journal experiments** before their PCSX starts; VERIFY after positive execution and again after the negative experiment. The negative saved-word run must still be rejected by v144, and a v145 source/build-positive post-run recheck must confirm the host binary remained identical. Both positive and negative runs continue to use distinct independent 128-bit challenges, and all five genuine synthetic four-VBlank/three DMA2/five Unai timings remain unchanged.

Standalone GCC and Clang jobs compile a small **synthetic host ELF** and test both phases, wrong executable substitution, post-prepare executable byte mutation, symlinked ancestry, permissions, malformed/duplicate manifest keys, missing/changing nonce, altered instruction words and no private-data leakage.

### Evidence boundaries

A pre/post ELF hash **does not prove which bytes the OS actually executed between measurements**. It is not a signed/reproducible-build attestation, a measured-boot proof, a hardware PS1 comparison or evidence of original Vandal Hearts MAP02 executing. A malicious process with control of both source and protected files can forge the result. This improves **controlled laboratory build-identity consistency** and prepares later original-only local research. The public CI still contains no user's `SLUS_004.47`, retail executable ELF or original graphics. Nintendo Switch HD parity is unverified.

The PR remains Draft; `main` unchanged pending CI.
