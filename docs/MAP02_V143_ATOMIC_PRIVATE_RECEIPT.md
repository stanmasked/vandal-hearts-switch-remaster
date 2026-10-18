# MAP02 v143 — atomically publish private interpreter MMIO receipts

Stacked on [v142 Draft PR #134](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/134), which passed **36/36** GitHub Actions workflows. The pinned native PCSX ReARMed GCC and Clang jobs ran a source-authored synthetic PS-X EXE and emitted 19 ordered MIPS `SW` events from the **actual** `psxMemWrite32` call. The independent synthetic EXE/ELF reader accepted the genuine private receipt and rejected a deliberately corrupted saved instruction word.

### Why hardening was necessary

v142 protected its final output file using `O_CREAT|O_EXCL|O_NOFOLLOW` and mode `0600`, but only checked the **last output directory** for symlinks. An unsafe or symlinked ancestor could redirect the recording, and a process killed during writing could leave an incomplete final JSONL file visible to a later verifier. This stage removes both gaps **before enabling broader private original-MIPS research**.

The new `tools/apply_map02_v143_atomic_private_receipt.py` patches only the **private native writer**, preserving the existing interpreter PC/instruction/effective-MMIO/GPU-DMA observation and all four execution-stage checks. Its safety invariants are:

- Paths must be **absolute**, bounded by 4096 bytes, no empty, `.`, or `..` components; each component is at most 255 bytes.
- Open the kernel root directory, then walk **each** component with `openat(O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)`. Intermediate directories may belong to root or the current account but must not be writable by group or other users. The final target directory must be owned by the current account and have exactly `0700` permissions.
- Create only the fixed, new **staging file** `.vh143-private-mmio-staging.jsonl` with mode `0600`, `O_EXCL` and `O_NOFOLLOW`. Never write directly to the public final filename.
- Write all 19 canonical tuples; check bounded `snprintf` and full `write`, `fsync` the file and verify same inode, link count and permissions.
- **Atomically publish only complete bytes** using `linkat(staging, final)`. The final filename cannot overwrite an existing file or a symlink. Check the linked inode, unlink staging, and `fsync` the directory. On any failure, refuse and attempt to clean up only this process's newly created files.
- A process killed partway through writing leaves at most a private staging file **not** a partial published final receipt. An abandoned staging leaf causes future attempts to refuse rather than collide/race.
- The negative v142 mode still corrupts **only a saved receipt word**, never CPU/GPU/DMA state; the independent EXE/ELF verifier must reject it. Nothing about these controls attests an original game binary or MAP02.

### Evidence

Standalone GCC and Clang C11/bounds/UB sanitizer tests compile the *same native writer C source* and check complete mode-0600 publication, hard refusals on overwrites, stale staging, symlinked ancestors/leaf, unsafe ancestor permissions, traversal and malformed relative paths. Full pinned native GCC/Clang PCSX jobs run the unchanged v142 positive/negative synthetic MIPS receipt workflow using this upgraded writer. Only the public status summaries are uploaded; actual receipts remain in `proof/private/`.

**Explicit limitation:** this is a private file-integrity and synthetic runtime-capture milestone. The retail original `SLUS_004.47` has not run in public CI. Native producer cryptographic attestation, retail MAP02 gameplay, physical PS1 parity and Nintendo Switch HD graphical equivalence are **unverified**.

Original EXE and trace files must remain outside public GitHub Actions artifacts.
