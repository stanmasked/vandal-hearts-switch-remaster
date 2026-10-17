# MAP02 v101 — independently reopened final private file and parent-directory fsync

The pinned PCSX ReARMed v100 emulator completed the full GCC+Clang
native software-GPU matrix: four authentic emulator VBlank callbacks,
2,380 synthetic MIPS VRAM readbacks, 4,137 ordered private events
without drops, and original mode-0600 v82 exclusive publication.

The v100 publisher synced the temporary file, verified its bytes,
hard-linked to a new final filename, synced the parent directory,
removed the owned temporary stage, and synced the parent again.
This is stronger than a file-only fsync but the final pathname
was not independently reopened and verified before returning success.

## The private-publisher contract

v101 changes the **same native v82 publisher**, not Switch rendering.
Before a successful publish can be returned, it invokes the new
`vh101_verify_private_commit(path, expected_bytes, expected_size)`.

The verifier:

1. Reopens the parent with `O_DIRECTORY|O_NOFOLLOW` and checks that
   the descriptor identifies a directory.
2. Requires the v99 state for the final file to be exactly **1**
   (completed final, **no remaining stage**). Existing ambiguous
   two-hardlink states, a leftover `.tmp`, unsafe mode, or symlink
   are refused rather than reinterpreted as successful publication.
3. Independently opens the final inode using `O_NOFOLLOW`; requires
   a regular, single-link, mode-0600 file of exactly the expected size.
4. Reads the complete final file and compares **every byte** to the
   originally supplied private event buffer, rejects unexpected EOF
   or trailing data, and fsyncs the **reopened completed file**.
5. Fsyncs the **separately reopened parent directory** and then
   compares the original file descriptor with the pathname's later
   device, inode, size and mode metadata.
6. Only after all of these checks and both closes succeed is the
   verification counted as successful.

If the readback, either fsync, metadata, reopen or close fails,
the publisher returns failure even though a final filename may
already exist. It **does not delete, replace, or automatically retry**
that possibly committed file. Recovery is possible only with a
different previously unused private filename, as in v98–v100.

These checks are software POSIX syscall validations within a private
directory, not a physical power-loss experiment and not a solution
for arbitrary hostile concurrent filesystem writers.

## Isolated deterministic native failures

GCC and Clang native C tests link the *real*
`map02_v82_private_publish.c` with the test-only
`VH100_FAULT_TEST` macro, which enables `vh101_test_fail_at`
to inject failure while checking the newly opened parent metadata,
fsyncing the **committed file**, or fsyncing the **reopened parent**.
In every injected failure the result must be refusal, the previously
linked final pathname and its bytes must remain untouched, and any
retry with the same target is refused. A separate fresh filename
must succeed when the fault has been cleared.

Other adversarial tests verify wrong expected bytes/size,
post-commit modification, weak permissions, symlinked final or
parent path, and an unexpected leftover temporary stage.
The independent verifier never cleans up data it does not own.

## Pinned full native emulator and private provenance

After original four VBlank events, 2,380 VRAM checks, genuine pinned
Unai render/async GPU worker paths, and every v80–v100 opt-in
diagnostic, v101 publishes two small **host-generated private-only
marker files**. Each successful original v82 publication now
performs one completed-inode reopen check and one parent resync.
The fixture explicitly re-verifies both markers, bringing the count
to four each, then proves that a wrong byte buffer is refused
without increasing either success count. Recovered test markers
are removed by the test; the canonical v82 private journal
destination is untouched until the original final export.

Three ordered bounded native aggregate observations attest the
four successful reopened validations, four reopened parent syncs,
and the refused mismatching expected bytes. The independent
Python auditor recomputes the full original v80–v100 provenance
before permitting the v101 suffix. CI uploads only aggregate PASS
summaries, never the private journal or VRAM content.

### Honest scope

This is a synthetic host-control validation inside the pinned PCSX
ReARMed software renderer, **not** a hardware PS1 or genuine retail
MAP02 timing proof. No real power interruption was simulated,
the production Nintendo Switch HD replacement is OFF, and
`main` is unchanged.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
