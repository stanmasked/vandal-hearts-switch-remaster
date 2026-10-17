# MAP02 v100 — persist private journal directory entries

The pinned PCSX ReARMed v99 native emulator validated four
**emulator** VBlank callbacks, 2,380 synthetic MIPS oracle VRAM samples
and 4,134 private events without drops, including deterministic recovery
when the original restricted private export left an incomplete `.tmp`.

v100 strengthens the filesystem durability contract of the **same**
mode-0600 exclusive v82 POSIX publisher.

## Parent directory synchronization

The original v82 sequence writes a new temporary file using
`O_CREAT|O_EXCL|O_NOFOLLOW`, fsyncs its contents, reads back the full
bytes and creates the final name using an exclusive hard link (never
`rename` replacing a prior generation).

v100 retains that exact no-clobber protocol, but opens the target's
parent using `O_DIRECTORY|O_NOFOLLOW` and introduces two mandatory
parent-directory durability boundaries:

1. After successful `link(tmp,final)`, **fsync(parent_dirfd)**.
   File-content fsync alone is not evidence that the new pathname
   has been persisted by the filesystem.
2. After successful `unlink(tmp)` (only the newly owned stage),
   **fsync(parent_dirfd)** again, to request persistence of the
   removal of the temporary filename.

Each required fsync error forces publication to return failure.
If the final hard link was already created when the failure occurred,
the publisher does **not** delete/rollback that existing final name.
If the stage has not yet been removed, it is also retained for explicit
inspection. A retry using the same final filename is refused and must
select a new distinct private name. Successful fsync calls increment
one bounded **aggregate integer counter**: no raw private event, pixel
or filesystem content is logged publicly.

This improves filesystem-level durability on supported POSIX
filesystems, but does not establish physical power-loss behavior,
specific storage-device flush correctness or atomicity against an
external adversarial concurrent filesystem writer. Runtime checks
are a software proof of successfully returned sync system calls.

## Deterministic native failure phases

Isolated GCC and Clang native C tests compile the real
`map02_v82_private_publish.c` with **`VH100_FAULT_TEST` only**.
Three deterministic negative gates emulate failure after:

- creating the exclusive final hard link, before parent fsync;
- successful first parent fsync, before staged-file deletion;
- staged-file deletion, before the second parent fsync.

Each tested phase returns an error; the already-linked final file is
still present and cannot be replaced. Depending on the phase, the
stage may also remain. A subsequent successful generation must use a
**different unused filename**, preserving old bytes. Other native
tests verify normal publication performs *exactly two* successful
parent-directory syncs, refuses existing stages, and rejects
symlink/unsafe/traversal path handling.

The fault gate is **not** built into the pinned full emulator or
production paths.

## Pinned full-emulator smoke

After all original four emulator VBlanks, 2,380 MIPS VRAM oracle
samples, real Unai software GPU commands, original async GPU worker
controls and v80–v99 strict host diagnostic checks, v100 creates two
short synthetic marker files under the existing **private** test
directory. Both are written through the original v82 publisher;
the native sync count must increase by two per successful file.
An attempted duplicate publication must fail with no extra directory
syncs. Byte-exact readback validates both independent marker
contents before removing only those owned test markers.

The real canonical full private journal remains published once by
v82 after v100's three bounded audit observations. Independent v100
private JSONL verification requires original v80–v99 provenance plus
two post-link and two post-unlink directory syncs and refusal of
duplicate publication. GitHub Actions checks the real native
GCC/Clang workflow, including the protected journal's exact byte
length and SHA-256 validation, and uploads only non-sensitive
aggregate summaries, never private GPU traces.

## Limitations

Synthetic pinned emulator host controls are **not original retail
Vandal Hearts MAP02** and cannot confirm real physical PlayStation
timing or Nintendo Switch HD replacement correctness. `main`
is unchanged and HD rendering remains disabled.

`original_retail_MAP02_verified=false`
`physical_ps1_vblank_verified=false`
`HD_replacement_approved=false`
