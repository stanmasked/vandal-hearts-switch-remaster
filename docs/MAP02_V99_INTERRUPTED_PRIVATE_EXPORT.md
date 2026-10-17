# MAP02 v99 — interrupted private .tmp export and no-clobber restart

The pinned PCSX ReARMed v98 proof verified four real **emulator** VBlank
callbacks, 2,380 signed synthetic MIPS VRAM samples, and a private
byte-exact journal with 4,131 events (zero drops). Original retail
Vandal Hearts MAP02 and physical PlayStation timing remain unverified.

v99 adds a *specific* recovery test for the state left when a private
file write is interrupted **before** the v82 `link(tmp,final)` commit.

## New native POSIX private-state classification

`vh99_private_state(final_path)` is read-only; it examines `final_path`
and `final_path.tmp` using **lstat**, never following links, and
requires existing files to be regular, mode 0600, with one hard link.
It distinguishes:

| Result | Final | Temp stage | Meaning |
|---|---|---|---|
| 0 | absent | absent | Fresh destination |
| 1 | present | absent | Completed publication |
| 2 | absent | present | Interrupted/uncommitted stage |
| 3 | present | present | Completed final with leftover stage |
| -1 | unsafe/error | unsafe/error | Refuse |

A partial temporary file is **never interpreted as an already
completed journal**, regardless of its contents or length. Both
unsafe symlinks and weakly protected staging files are refused.

`vh99_publish_after_interruption(abandoned_final,fresh_final,bytes,size)`
requires the old state to be exactly **2**, a distinct target in
state **0**, and valid bounded paths and a nonempty private payload.
It delegates publication exclusively to the original v82 code,
which uses `O_EXCL|O_NOFOLLOW` for the new temporary file,
`fsync`, byte-exact readback and a no-replace final hard link.
It then checks the original old stage's inode, size, file mode and
link count remained unchanged, while the recovered final has state
**1**. This never deletes or reuses the interrupted stage. The caller
must explicitly choose a fresh filename. A duplicate replay is
refused.

This provides fail-closed behavior within an **exclusively owned**
private directory, not an atomic defense against arbitrary
simultaneous malicious filesystem changes or device-level power-loss
durability. Existing v82/v98 protections stay enabled.

## Real emulator host-only test

After all v80–v98 oracle and GPU-worker controls have finished and
`GPUfreeze` drained the pinned native worker, v99 creates a small
incomplete **synthetic marker file** at
`private/<trace>.v99-lost.tmp`, leaving the corresponding final
missing. The actual private v82 publisher refuses to use that occupied
stage or the same interrupted filename. The recovery helper accepts
only the new `private/<trace>.v99-fresh` destination. A replay is
refused; the abandoned stage and fresh file are both read back byte
for byte. Only test-owned marker files are subsequently removed.

The canonical original `VH_MAP02_V82_PRIVATE_PATH` is **not changed**
by this test. The real full VBlank/MIPS/GP0 journal is then exported
through the unchanged v82 private publisher and independently
verified, including mode 0600 and SHA-256 readback in GitHub Actions.

Exactly three new bounded private aggregate observations are appended
to the journal after the v98 checkpoint. A strict v99 independent
Python audit refuses duplicated, truncated, forged, reordered or
out-of-range records and checks every v80–v98 predecessor.

## Isolated native C negative tests

The pinned GCC and Clang matrices additionally compile the real v82
publisher with the new v99 helpers and exercise eight interrupted
states: truncated old stage, zero-length partial stage, pre-existing
completed final, final with leftover stage, symlink attack, insecure
mode, foreign fresh `.tmp`, occupied fresh final, path traversal and
missing old file. All negative cases refuse publication while leaving
existing old bytes and foreign files unchanged. At no point is the
original source trace uploaded as a GitHub public artifact.

The evidence concerns a **host-generated diagnostic fixture**, not
retail MAP02, original PlayStation physical GPU behavior, or the
Nintendo Switch HD replacement path. `main` is untouched.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
