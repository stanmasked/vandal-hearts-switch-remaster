# Switch Filesystem Smoke Test

A separate libnx diagnostic for the SD-card filesystem API. It contains no Vandal Hearts game code or data.

## What it checks

- Mounts the SD card through `fsdevMountSdmc()`.
- Creates `sdmc:/switch/vandal-hearts-switch-remaster/` if needed.
- Writes a small known payload to `fs-smoke-test.tmp`, flushes/closes it, reopens it, verifies exact bytes and EOF, then removes it.
- Refuses to overwrite an existing file with that name.

The directory is left in place. If the app is interrupted, the temporary file may remain; remove it manually before rerunning. This is a basic API smoke test, not a power-loss durability test and not evidence that the full game's file I/O is ported.

## Build

With devkitPro/libnx installed and `DEVKITPRO` configured:

```sh
cd switch-test-filesystem
make
```

The output is `switch-filesystem-smoke-test.nro`. Run it in your normal homebrew environment with an SD card mounted. The on-device result must be recorded separately from CI compilation.

## Expected result

The screen should report `PASS: write/read/compare/remove`. Press **+** to exit. On failure, the app displays the failing operation and may leave the temporary file only if cleanup itself failed or the app was interrupted.
