# MAP02 v104 — second full private read after fsync, same-inode tamper refusal

The prior v103 pinned PCSX ReARMed matrix completed 24 successful
GitHub Actions workflows, including GCC and Clang full software-GPU
emulator runs, four authentic emulator VBlank callbacks, 2,380
synthetic MIPS VRAM readback samples and a private 4,146-event journal
(302,452 bytes, zero drops).

The v101–v103 private publisher already rejects symlinked intermediate
components, checks the original final inode identity, uses no-replace
hard-link publication anchored to one `dirfd`, and fsyncs the private
file and parent directory. The remaining gap is a writable file whose
**inode remains the same but its contents change while the final
verification is executing**.

## Two full file passes and metadata consistency

`vh101_verify_private_commit` now requires two independent complete,
exact-length reads of the committed final file. The first one takes
place before `fsync(fd)` and `fsync(dirfd)`; the second one seeks back
to offset zero and rechecks every byte **after** those fsync operations.
It rejects short, extra or changed bytes. The native `fstat` check
also requires that the inode's `st_mtim` and `st_ctim` (seconds and
nanoseconds) agree with the metadata captured before the first read,
in addition to all earlier inode identity, size, single-link, mode-0600
and missing-`.tmp` tests.

No failed verification increments the successful-double-read counter.
After a failure the already linked file is retained, never removed,
replaced or silently retried using the same name.

## Isolated deterministic same-inode mutation tests

GCC and Clang compile the *real* C publisher with the isolated
`VH100_FAULT_TEST` macro. Three controlled one-byte in-place writes
to the same original inode and unchanged file size are injected:

1. After the first full read, before `fsync(fd)`;
2. After the file fsync but before the parent directory fsync;
3. After both fsyncs but before the second full read.

Every phase must return refusal. The tests independently check the
original inode identity and file size, the changed bytes, zero new
successful double-read and publish counters, refusal of a duplicate
final name, and successful publication using a different fresh name.

The fault hook is absent from the ordinary pinned PCSX build.

## Pinned full-emulator host-only smoke

All earlier v80–v103 original software Unai/GPU worker and synthetic
four-emulator-VBlank/MIPS controls remain mandatory. After
`GPUfreeze`, v104 creates two **private-only synthetic marker files**
through the same original native v82 exclusive publisher. It performs
two additional independent final-content verifications, proving four
successful second-pass reads. Then it changes one byte of one of its
own private test markers *in place*, verifies that the original bytes
are rejected without incrementing the success counter, explicitly
restores its owned marker and removes only the two owned test files.

Three bounded private aggregate events are checked by the strict
independent v104 Python auditor. The canonical original full private
journal is then exclusively published by the v82 exporter and
revalidated for exact bytes, private permissions and SHA-256. Raw
traces, game assets and VRAM are never public CI artifacts.

## Limits of the claim

The second read and timestamps detect the deterministic modifications
tested here. They are **not** an atomic snapshot against arbitrary
hostile writers changing bytes after the final read, nor a proof of
power-loss durability or fsync behavior on physical media. The private
directory must remain exclusively owned for trustworthy results.

This is synthetic host-controlled pinned emulator evidence, not
retail Vandal Hearts MAP02, physical PlayStation GPU timing, or
Nintendo Switch HD renderer equivalence.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`

Draft stacked on v103; `main` untouched.
