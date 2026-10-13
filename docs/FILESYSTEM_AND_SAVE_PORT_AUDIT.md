# Filesystem, disc-image, and save-data port audit

Status: static source audit only. No Switch filesystem backend is implemented or tested here.

Audited upstream revision: `14552fffa0e0b47e02b57592e274fc6e7a649923`.

## Findings

### Disc image and boot configuration

- `platform/pc/src/libcd.c` mounts a user-selected raw disc image with `fopen(path, "rb")`, retains a process-global `FILE *`, and seeks/reads 2352-byte raw sectors. `PC_CdImageBytes()` uses `fseek/ftell` to validate image length; the sector reader expects raw-sector layout and validates sync/address bytes.
- `platform/pc/src/pc_bootstrap.c` discovers the executable directory using OS-specific APIs (`GetModuleFileNameA`, `_NSGetExecutablePath`, or `/proc/self/exe`), looks for `vandalhearts.ini`, and uses environment variables for overrides. It also includes OS-specific executable inspection and fixed-address memory setup, so it is not a Switch startup module.
- Relative paths and the desktop deploy-directory convention are not a suitable implicit contract for a Switch app. The Switch backend must define an explicit user-data root and how the user selects a legally obtained disc image. Do not package an image or BIOS.

### Save data

- `platform/pc/src/pc_saves.c` treats the active memory-card image as a region-specific file, and implements archive/list/restore/delete operations under a `saves/.archive` directory.
- Archive copies use a sibling temporary file, flush/sync the file, rename it into place, and on POSIX also attempt to sync the parent directory. The POSIX implementation uses `mkstemp`, `fdopen`, `fsync`, `fileno`, `rename`, `mkdir`, `stat`, and `dirent`-style listing operations. The Windows implementation has separate `MoveFileExA` and `_commit` handling.
- `PC_SaveIniConfig()` writes a fixed `vandalhearts.ini.tmp` path and then replaces the configuration; its behavior and failure recovery need review separately from save-card archiving. A fixed temp name can collide with another writer and must not be assumed crash-safe on a new backend without tests.
- The archive layer validates archive names and checks card structure/checksums before restore. Preserve these validations if the save backend is adapted; do not replace them with unchecked path concatenation or raw restore.

### Diagnostics and optional content

- The PC backend has optional diagnostic CSV/trace/log output, HD-pack manifests, WebP assets, and MP4 replacements opened by path. These are not baseline boot requirements and should be disabled or redirected to a writable diagnostics directory during the first Switch integration pass.
- Hard-coded desktop paths (for example temporary video dumps) and environment-variable toggles must not leak into the target build.

## Switch integration contract

Before wiring the game engine to a Switch filesystem, document and test these choices:

1. **Mount and path policy:** initialize the intended libnx filesystem service(s), define the writable root (including whether SD-card access is enabled), normalize separators, and keep user files separate from bundled read-only content.
2. **Disc input:** provide an explicit path/configuration mechanism for a user-supplied raw image; validate file length and read errors; confirm random-access seeking and large-file behavior under the selected filesystem API.
3. **Save durability:** choose the save location and replacement strategy. Verify partial-write, flush, close, rename/replace, and power-loss behavior; retain region and card-format validation. If directory sync or atomic replacement differs from desktop POSIX, record the substitute guarantee rather than assuming equivalence.
4. **Concurrency:** define whether save/config operations can overlap; avoid fixed temporary names if concurrent writers are possible.
5. **Error reporting:** translate missing image, unsupported region, malformed card, full storage, and I/O failures into user-visible messages instead of desktop stderr dialogs.
6. **Build boundary:** exclude desktop bootstrap, debug dumps, optional HD asset loaders, and desktop-only path discovery from the initial Horizon target unless each is deliberately ported and tested.

## Verification gate

- [ ] Build a target-specific filesystem adapter without compiling `pc_bootstrap.c`.
- [ ] Test missing/invalid image, truncated image, failed seek/read, and valid user-provided image on target or an appropriate test environment.
- [ ] Test save creation, overwrite, archive, restore, delete, invalid archive names, full-storage/error paths, and interrupted writes.
- [ ] Confirm both supported region formats remain isolated and validated.
- [ ] Confirm optional diagnostics and HD replacements default off and cannot write to an unexpected path.
- [ ] Record real-device results separately from host tests and CI compilation.

This audit is based on source inspection; it does not establish that the upstream save or disc code is compatible with Horizon/libnx.
