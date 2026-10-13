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

1. **Started:** add a small, host-testable checked path joiner. The initial helper is in `switch-save/checked_path.c`; it rejects empty, traversal-like, multi-component, control-character, and overlong leaf paths without modifying the output on failure. Its root is trusted input and must be chosen by the target backend.
2. **Prototype added:** `switch-save/card_validate.c` validates an in-memory card image without file I/O. Host tests synthesize US (384-byte) and JP (512-byte) header layouts, check valid occupied slots, and reject a bad header, listing CRC, occupied-slot CRC, or truncated occupied record. CI compiles this module with strict warnings.
3. **Prototype added:** `switch-save/atomic_write.c` coordinates a backend-provided temporary-file write, flush, close, and replacement. Mock-backed host tests inject open, write, flush, close, and replace failures; failed transactions do not replace the existing mock destination and clean up the temporary file when available. CI compiles this module with strict warnings.
4. **Prototype added:** `switch-save/card_restore.c` validates the complete in-memory card image and requires its detected header layout to match the expected region layout before it calls the atomic-write orchestrator. Host tests prove invalid CRCs and region mismatches do not even open a temporary file; a valid synthetic image reaches the write seam. This remains an orchestration prototype, not a filesystem-backed restore.
5. **Prototype added:** `switch-save/archive_name.c` restricts archive basenames to the active card's trusted region-specific prefix, a non-empty suffix, and a small ASCII character allowlist. It rejects names containing repeated dots, separators, spaces, and other unsupported characters. Host tests cover US/JP prefix separation and malformed names.
6. **Prototype added:** `switch-save/archive_reader.c` validates the archive basename before opening it through a backend callback, reads into caller-owned bounded memory, and requires both the read and close callbacks to succeed before card validation and atomic replacement begin. Host tests inject read failure, close failure, oversized reported length, an empty archive, an undersized caller buffer, and traversal-like names; these cases do not open a destination temporary file.
7. **Prototype added:** `switch-save/archive_path.c` combines the region-specific archive-name allowlist with the checked single-component path joiner. Host tests verify a valid path, wrong-region and traversal rejection, and unchanged output on failure or insufficient capacity. The root remains trusted backend input; this helper does not validate mounts or symlinks.
8. Implement concrete platform callbacks with unique same-filesystem temporary files and documented replacement semantics; do not compile desktop POSIX/Windows path and sync code into Horizon.
9. Run real-device tests for SD removal, storage errors, restart recovery, and region isolation before connecting the save UI.

The archive-name helper is a basename allowlist, not a filesystem security boundary by itself; the archive-path helper combines it with the checked path joiner, but still depends on a trusted root and does not validate mounts or symlinks. The checked-path helper is only a small path-construction primitive; it does not create directories, verify mount state, resolve symlinks, or make file replacement atomic. The card validator only checks the observed header/listing/occupied-record CRC structure in a caller-provided byte buffer; it does not read files or establish game-specific region identity independently of the expected header layout. The restore coordinator joins validation to the atomic-write interface and rejects invalid images or mismatched expected header sizes before any write callback runs. The archive-reader prototype validates the basename before opening via a backend callback and requires successful bounded read and close before delegating to restore; it still does not implement filesystem I/O, establish the archive root, or discover region from trusted game configuration. The atomic-write orchestrator is only a callback sequence and mock-test seam: it does not implement libnx I/O, guarantee that a backend's replacement is atomic, or provide power-loss durability itself. None of these helpers is wired into the game or save backend.

Do not package game data, BIOS files, or disc images in the repository or build artifact.
