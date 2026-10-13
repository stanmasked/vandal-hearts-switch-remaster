# Save-data failure matrix for the Switch port

Status: source-derived test plan; no save backend has been ported or run on a Switch.

Audited upstream revision: `14552fffa0e0b47e02b57592e274fc6e7a649923`.
Primary source: `platform/pc/src/pc_saves.c`.

## Existing desktop behavior to preserve

- Active memory-card file is selected by region: US `BASLUS-00447VH`, JP `BISLPM-86007VH`.
- Archives live under `saves/.archive`, use the active-card prefix, and are filtered by `validArchiveName()`.
- Restore validates card header/listing and occupied save-record checksums before copying.
- Archive and restore copies write a sibling temporary file, check read/write errors, flush and sync the file, close it, then replace the destination. POSIX additionally attempts to sync the parent directory; Windows uses its own replacement/commit calls.
- Archive listing ignores non-regular files, sorts newest first, and marks archives byte-identical to the active card.

These are desktop-source observations, not guarantees about a future Horizon implementation.

## Portability and failure risks found in source

1. **Directory creation result is ignored.** `PC_SaveBackupCurrent()` calls `makeDir(adir)` and ignores the result. A target adapter must distinguish “already exists” from permission, mount, and storage errors.
2. **Temporary-file collision policy differs by platform.** POSIX uses `mkstemp` with exclusive creation. Windows uses a PID-derived name and `fopen("wb")`; this is not an equivalent exclusive-create guarantee. The Switch implementation should use a collision-resistant/exclusive strategy supported by its filesystem layer.
3. **Durability guarantees are not interchangeable.** The desktop code attempts file sync and, on POSIX, parent-directory sync; the Windows path uses `MOVEFILE_WRITE_THROUGH`. A libnx implementation must document which operations exist and test the actual failure semantics instead of claiming POSIX-equivalent power-loss safety.
4. **Some path builders do not propagate truncation.** `activePath()`, `archiveDirPath()`, and `archivePath()` call `snprintf` without checking its return value. The target adapter should centralize bounded path construction and reject truncation.
5. **Timestamp generation uses process-global local time.** `localtime()` and second-resolution archive names can collide. The source adds a numeric suffix when a destination exists, but simultaneous writers are not serialized. Define whether saves can run concurrently before porting this logic.
6. **Restore replaces the active card atomically only to the extent of the platform implementation.** Preserve the validation-before-copy order, and test that a failed copy/replace leaves the prior active card intact.
7. **Active-card reading does not check the final close result.** `readActiveCard()` checks size and stream errors but ignores `fclose()`. A strict target-side read helper should report close/I/O errors consistently.
8. **Archive deletion is irreversible at the API level.** `PC_SaveDeleteArchive()` removes the archive directly. UI confirmation and error reporting belong above the filesystem adapter; deletion must never accept a path outside the validated archive namespace.
9. **Config replacement is a separate transaction.** `PC_SaveIniConfig()` uses a fixed `vandalhearts.ini.tmp` name (see the filesystem audit). Do not assume the archive copy helper protects configuration writes.

## Required test matrix before enabling saves in the game

| Scenario | Expected invariant |
|---|---|
| Save root absent | Create only the intended user-data directories; report creation/mount failures |
| Storage full during temporary write | Return failure; do not replace the existing destination |
| Short write, flush, sync, or close error | Return failure and clean up the temporary file where possible |
| Replace/rename fails | Existing active card or archive remains readable and unchanged |
| Process interrupted before replace | Destination remains the old complete file; stale temporary files are safely ignored/cleaned |
| Process interrupted after replace | Destination is a complete validated card; durability claim matches tested filesystem behavior |
| Two archive requests in one second | Unique archive names; no accidental overwrite |
| Two writers overlap | Explicitly reject/serialize or prove independent temporary files and safe replacement |
| Wrong-region archive | Reject restore without modifying the active card |
| Invalid archive name / traversal-like name | Reject before any filesystem operation outside the archive namespace |
| Truncated card, bad header, bad listing CRC, bad occupied-slot CRC | Reject restore; active card remains unchanged |
| Archive directory missing | Listing returns an empty list; other I/O failures are distinguishable from “empty” |
| SD card removed / filesystem unmounted | Fail cleanly, surface an actionable message, and avoid using stale handles |
| Config write interrupted | Old config remains usable or recovery behavior is documented and tested |

## Implementation order

1. Add a small target-specific filesystem/path adapter with checked joins and explicit user-data root.
2. Keep card validation independent of file-opening details so it can be host-tested using synthetic fixtures.
3. Port archive operations behind the adapter; avoid compiling desktop POSIX/Windows path and sync code into Horizon.
4. Add fault-injection tests for write/flush/close/replace failures on the host.
5. Run real-device tests for SD removal, storage errors, restart recovery, and region isolation before connecting the save UI.

Do not package game data, BIOS files, or disc images in the repository or build artifact.
