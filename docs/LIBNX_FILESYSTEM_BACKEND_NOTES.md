# libnx filesystem backend findings

Status: source/API audit only. No Horizon backend has been implemented or tested on a console.

Reviewed libnx interfaces and implementation from the public `switchbrew/libnx` repository (current source snapshot inspected during this audit):

- [`fs_dev.h`](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/runtime/devices/fs_dev.h) exposes `fsdevMountSdmc()`, `fsdevCommitDevice()`, and `fsdevTranslatePath()`. The header explicitly says `fsdevCommitDevice()` must be used after savedata writes, including after file close; it is not called automatically on unmount.
- [`fs.h`](https://github.com/switchbrew/libnx/blob/master/nx/include/switch/services/fs.h) exposes `fsFileFlush()` as a result-returning operation, but `fsFileClose()` returns `void`. A direct libnx adapter therefore cannot report a close error through the current `vh_atomic_write_ops.close` contract; it must not pretend that a successful close result was observed.
- [`fs_dev.c`](https://github.com/switchbrew/libnx/blob/master/nx/source/runtime/devices/fs_dev.c) implements `rename()` by calling `fsFsRenameFile()` after querying the source entry type. This establishes that a rename API exists, but the inspected wrapper does not establish overwrite behavior, atomicity, or power-loss durability for an existing destination.
- The same source snapshot's `fsdev_close()` contains `Result rc=0`, calls `fsFileClose()` without assigning its result (the API returns `void`), then tests `R_SUCCEEDED(rc)`. This makes stdio `fclose()` an unsuitable basis for claiming that the underlying libnx close operation itself was verified. Writes and flushes still need explicit error checks.

## Consequences for the save adapter

1. Do not implement `replace` as an assumed-safe `rename()` until replacement semantics on the actual target filesystem are established. In particular, do not delete the old destination first: a subsequent rename failure would lose the previous save.
2. A direct `FsFile` backend can check every `fsFileWrite()` result, verify the reported byte count for reads, and check `fsFileFlush()`. Since `fsFileClose()` returns no status, document that limitation rather than synthesizing a close-error guarantee.
3. Decide whether the target is an SD-card path or application savedata. `fsdevCommitDevice()` is documented for savedata writes; do not apply or interpret it as a universal SD-card durability guarantee.
4. Use an exclusive-create strategy for temporary files if supported by the selected API. The `fsdev_open()` implementation maps `O_CREAT | O_EXCL` to `fsFsCreateFile()` and reports creation failure, but this alone does not prove safe replacement of the destination.
5. Before enabling restores, test rename-over-existing behavior, interrupted writes, storage removal, and recovery on the actual target filesystem. Until then, keep the callback orchestrator disconnected from the game.

This audit informs implementation choices; it is not a hardware test report and makes no claim that any Switch save operation is atomic or power-loss safe.
