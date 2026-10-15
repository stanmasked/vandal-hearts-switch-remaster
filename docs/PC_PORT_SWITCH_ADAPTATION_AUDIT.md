# PC-port to Switch: source boundary audit

## Scope and source pin

This is a source inspection of `HalmyLyseas/VandalHearts-PcPort` at audited revision `14552fffa0e0b47e02b57592e274fc6e7a649923`. It is not a Switch build or runtime result.

## Confirmed platform seams

### Startup and fixed PlayStation memory

`platform/pc/src/pc_bootstrap.c` contains OS-specific startup behavior:
- Windows reserves fixed PS1 RAM addresses with `VirtualAlloc` and uses `VirtualProtect` for executable/section permissions.
- POSIX uses `mmap` with `MAP_FIXED_NOREPLACE`, and includes signal/context handling for Linux x86-family paths.
- macOS has separate Mach-O image/segment handling and does not use the same bootstrap path as non-Apple builds.
- The PC port expects a 2 MiB region at `0x80000000` and a 1 KiB scratchpad at `0x1f800000`; comments explicitly warn that hardcoded addresses in decompiled code can fail if these reservations fail.

**Switch consequence:** do not carry these desktop APIs over mechanically. Before choosing a Switch memory strategy, inventory every absolute address / section-protection assumption and prove address translation or reservation works under the actual Switch process layout. A successful GLES2 presenter probe does not validate these memory assumptions.

### Video output

`platform/pc/src/pc_gpu_window.c` is a desktop host presentation layer around the software GPU. It includes SDL2, uses an SDL renderer/texture on macOS and OpenGL on non-Apple desktop platforms, and owns the host window/presentation resources. The Switch GLES2 RGB24 presenter in this repository is a separate reusable module, not yet wired into the upstream game renderer.

**Switch consequence:** the integration seam should be the completed frame buffer boundary, not the game logic or rasterizer. Preserve the audited RGB24 contract (packed rows, `width * 3` stride, bottom-up orientation, RGB order) and consume/copy the call-scoped frame before its source buffer can be reused. Verify with captured real-game frames before claiming visual parity.

### Save-file operations

`platform/pc/src/pc_saves.c` implements desktop file operations with platform branches:
- Windows uses `MoveFileExA` with replace/write-through flags, `_commit`, and Windows process/file APIs.
- POSIX uses `mkstemp`, `fdopen`, `fsync`, `rename`, and parent-directory syncing.
- The archive names are filtered to the active regional card prefix; archive storage is kept under a dot-prefixed `.archive` directory.

**Switch consequence:** replace or adapt the filesystem calls against the chosen Switch filesystem API, then retain the transactional properties as explicit requirements: temporary sibling file, complete write, flush/sync where supported, atomic replacement where supported, and region-prefix validation. Existing host save tests do not prove Horizon filesystem durability or permissions.

### CD-XA audio

`platform/pc/src/pc_xa.c` combines XA ADPCM sector decoding with an OpenAL streaming source and buffer queue. The decoder carries per-channel predictor history across sectors; OpenAL is the host-specific output layer.

**Switch consequence:** keep decoder behavior isolated from audio-device output. The current CI audio probe is inconclusive without a usable host audio device, and the synthetic CD-XA tests do not establish correct decoding of the user's real disc or audible playback on Switch. Test decoding against known sectors/PCM reference, then implement and test a Switch audio sink separately.

## Integration order

1. **Memory/bootstrap inventory:** enumerate absolute-address use, fixed mappings, section permission changes, constructor-order dependencies, and platform macros.
2. **Frame boundary:** add a narrowly scoped adapter from the real software-GPU completed frame to the already-tested RGB24 presenter; add a real-frame screenshot comparison test.
3. **Input:** map Switch controls into the existing platform input contract without altering gameplay rules; test menu, tactical cursor, confirm/cancel, and analog/digital edge cases.
4. **Filesystem/save:** implement the active card path and transactional save/restore behavior using the target API; preserve existing failure semantics.
5. **Audio:** validate XA decoding with real source sectors before integrating a Switch output path; separately cover SPU/music/effects and lifecycle.
6. **Target verification:** build with devkitA64/libnx, run in emulator, then confirm on physical hardware. Keep each claim limited to the evidence from that stage.

## Status

- Source-level seams above: **inspected** at the pinned revision.
- GLES2 RGB24 presenter: **component-level prototype exists** and has host/probe coverage.
- Real game renderer connected to the Switch presenter: **not yet done**.
- Actual game image validated end-to-end: **not yet done**.
- Full Switch-target build and physical console launch: **not yet confirmed**.
