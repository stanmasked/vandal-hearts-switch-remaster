# MAP02 v190 — private native log stability across adversarial replay

Base: [MAP02 v189 Draft PR #220](https://github.com/stanmasked/vandal-hearts-switch-remaster/pull/220). Initial v189 native GCC/Clang logs and full 82-workflow matrix passed on initial head 2942e89f; current v189 head e8311af9 has additional strict uniqueness tests and remains under CI verification.

**Purpose:** v189 verifies that 159 modified in-memory copies of the original ten synthetic guest PCSX ReARMed/Unai logs are rejected, but does not require the original underlying files themselves to keep the same bytes and identity throughout the replay. A file could otherwise be rewritten or atomically swapped between the baseline v188 check and the v189 replay without an explicit independent provenance failure.

The new v190 wrapper performs a no-follow, descriptor-bound SHA-256 and filesystem identity check of the same ten bounded private logs **before and after** v189's complete proof. Identity includes device number, inode, file mode, file size, modification time and change time. Sampling cross-checks lstat, the opened descriptor and lstat after reading, rejecting symlinks, oversized files, truncations and replacements during the read. The SHA-256 fingerprints are compared only in memory and **never printed or committed**. The ten run labels must also resolve to **ten distinct (device, inode) identities** so two labels cannot refer to the same hardlinked evidence file.

Only after all ten inputs remain identical and the v189 replay returns exactly 10 isolated process transcripts, 21 snapshots and 159 rejected adversarial mutations does v190 emit:

VH190_NATIVE_LOG_STABILITY_PASS modes=10 snapshots=21 mutations=159 sha256_unchanged=10 inode_unchanged=10 metadata_unchanged=10 original_retail=0

The independent GCC/Clang model tests verify unchanged original fixture files, intentional in-place append corruption, same-byte atomic replacement with a distinct inode, symlink, missing and oversized private logs. They also require the pinned native PCSX job to run the new wrapper **after** the existing v189 pass.

The additional proof detects modifications made during the bounded audit interval; it does not prevent privileged agents from tampering with the operating system or retroactively prove provenance of a synthetic guest executable. It is **not** evidence of original retail Vandal Hearts MAP02 execution or physical Nintendo Switch output. No private ROM bytes or original trace text are exposed.
