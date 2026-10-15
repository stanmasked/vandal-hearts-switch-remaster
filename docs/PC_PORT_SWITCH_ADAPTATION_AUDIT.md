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


## Additional source checks: constructor order, input, and frame handoff

### Constructor-order and bootstrap hazards

A targeted pass through `pc_bootstrap.c` confirmed multiple GCC constructor entry points, including a priority-101 constructor that loads configuration before code reads the `VH_*` settings, plus a separate startup constructor that initializes platform state/windowing before the game's `main()`. The file also contains OS-specific fault handling and section permission changes, including POSIX `mprotect` and Windows `VirtualProtect`.

**Implication:** Switch startup should be an explicit ordered init sequence, not a blind copy of GCC constructor behavior. Build an initialization dependency table (config → platform paths → memory mapping/address compatibility → disc mount → renderer/input/audio → game entry) and test failure cleanup for each stage. Do not assume the desktop fault handlers or writable-string-literal workaround are valid or necessary under Horizon.

### Input and exit behavior

In `pc_gpu_window.c`, `PC_GpuPumpEvents()` drains SDL events, exits immediately on `SDL_QUIT`, and turns a non-repeated Escape keydown into the overlay's quit-confirmation request. The same source comment says SDL keyboard state is refreshed for the game's `PadRead` path from the present/VSync path.

**Implication:** the Switch input adapter must preserve the existing game's polling semantics and distinguish a requested graceful exit from process termination. Map confirm/cancel/menu actions explicitly, avoid treating controller disconnect or transient event loss as quit, and test repeated presses and menu confirmation.

### Frame lifetime and presentation API

The desktop presentation code computes a centered aspect-preserving viewport each frame. On non-Apple desktops it submits the software-GPU buffer through legacy `glPixelZoom` / `glRasterPos2f` / `glDrawPixels`; the macOS branch updates an RGB24 streaming texture and vertically flips the bottom-up scratch frame. This reinforces that the portable seam is the final converted frame, while window/context creation, viewport and swap behavior are platform responsibilities.

**Integration acceptance criteria:** (1) frame pointer and dimensions are validated before upload; (2) the scratch buffer is consumed synchronously or copied before return; (3) top/bottom and RGB channel markers match the desktop reference; (4) resize/letterbox behavior is tested; (5) no SDL/OpenGL desktop symbols leak into the libnx target; (6) presenter resources are released before the graphics context is destroyed.

## Next implementation gate

Before touching the upstream renderer, add a small integration contract header or adapter interface on the Switch side and a host test for it. Only then connect the exact call site that owns the completed frame. Avoid editing `pc_gpu_window.c` until the platform-specific source split and its build-system inclusion rules are known; changing that desktop file prematurely risks breaking the reference build.


## Exact GPU presentation hand-off and build-system constraints

The upstream GPU subsystem documentation identifies the native frame as **320×240** and states that PC_GpuPresent converts the visible VRAM region selected by the active DISPENV from BGR555 to RGB before handing it to the platform presenter. Presentation occurs at the end of DrawOTag, not in PutDispEnv: the PC rasterizer is synchronous, and presenting earlier would expose the previous double-buffer slot. This is a concrete integration boundary, not merely an assumption that a window function happens to run after rendering.

The same source documentation confirms that desktop scaling is display-only nearest-neighbour scaling by default; optional internal-resolution supersampling is a separate path. The Switch adapter must therefore first preserve the native-frame path and compare it against a known desktop capture before considering any supersampling changes. The existing repository RGB24 contract describes the converted frame at the presenter boundary; do not confuse its RGB byte order with the software GPU's internal BGR555 representation.

**Build-system constraint:** upstream contribution guidance requires every new backend source to be registered in both platform/pc/Makefile and platform/pc/CMakeLists.txt; the Makefile has explicit per-source object rules, and a parity checker enforces the two lists. For Switch integration, prefer a separate target-specific adapter/source list or an explicit compile-time seam. Do not add libnx-only symbols to the shared desktop source list, and do not modify the byte-matching game layer to solve a presentation problem.

**Evidence:** upstream GPU subsystem overview: https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/pc-port/subsystems/gpu.md ; architecture and source-layer boundary: https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/docs/architecture.md ; contribution/build parity rules: https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/master/CONTRIBUTING.md

**Next gate:** add a Switch-side frame-view adapter contract and host tests for dimensions, pixel format, lifetime, and failure behavior; then make the build include it only for the intended target. Do not claim the game is integrated until the real PC_GpuPresent hand-off is exercised by a game frame.


## Completed isolated Switch frame bridge gate (2026-10-15)

The project now includes source/frame_handoff.h, source/switch_frame_bridge.h, and source/switch_frame_bridge.c. The bridge synchronously validates a borrowed packed bottom-up RGB24 frame, uploads it to the initialized GLES2 presenter, and draws it into the provided viewport. It does not swap buffers, own the input frame, create a graphics context, or call upstream game code. An upload failure prevents drawing; invalid dimensions and an uninitialized presenter are rejected before upload.

Host tests in tests/test_frame_handoff.c and tests/test_switch_frame_bridge.c exercise callback lifetime assumptions, row orientation, invalid layouts, upload failure, draw failure, and initialization/viewport guards. The CI job also compiles the bridge with GLES2 headers and -Wall -Wextra -Werror. Verified passing workflow: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38762953578 (commit 7b3603ed4542ad516d1eaef15d4f9fd1632bf602).

**Still required:** identify the exact native call-site arguments and ownership in the pinned upstream pc_gpu_window.c; implement a target-specific backend that calls vh_switch_present_frame from that boundary, with an initialized GLES2 context and explicit buffer swap. Compare real game frames against desktop captures and validate Switch-target linkage/runtime. These host tests do not validate real-game rendering, framebuffer allocation sizes, or hardware presentation.

## Verified pinned upstream present function (2026-10-15)

Inspected platform/pc/src/pc_gpu_window.c at upstream commit 14552fffa0e0b47e02b57592e274fc6e7a649923, lines 755-927. The exact signature is `void PC_GpuPresent(unsigned short *vram, int vramW, int vramH, int x, int y, int w, int h)`. Its static `s_rgbaScratch` is a packed, **bottom-up** RGB24 buffer allocated/reused to fit `w*h*3`. The normal path samples the visible VRAM rectangle and expands 5-bit RGB channels by bit replication. The HD movie path copies RGB24 rows in reverse order; native movie/subtitle mode can upscale the presented dimensions by 4. Subtitle overlays, battle-speed text, camera OSD and the options overlay are painted into the same scratch buffer before host submission.

**Precise Switch seam:** after the final `PC_GpuDrawOverlay(w,h)` call and before the platform-specific SDL/OpenGL/Metal viewport + draw + swap code. Construct `VhRgb24Frame { s_rgbaScratch, (size_t)w * 3u, w, h }` only after ensuring multiplication and allocation bounds. Pass it to `vh_switch_present_frame` synchronously, then perform the Switch target's own buffer swap. Keep the existing desktop backend unchanged and gate the Switch path at the target backend layer. The frame dimensions must be dynamic; do not hard-code 320x240. A dedicated target implementation should also replace SDL event pumping and host timing dependencies rather than pulling `pc_gpu_window.c` unchanged into libnx.

**Important upstream risk to address before integrating:** the pinned desktop code stores scratch capacity as `int` and computes `w*h*3` in signed integer arithmetic. The portable Switch backend must validate positive dimensions and multiplication bounds before allocation/upload; passing arbitrary untrusted dimensions through the desktop allocation expression would be unsafe. The RGB24 frame view validates layout arithmetic but cannot prove the backing allocation is large enough.

Source: https://github.com/HalmyLyseas/VandalHearts-PcPort/blob/14552fffa0e0b47e02b57592e274fc6e7a649923/platform/pc/src/pc_gpu_window.c#L755-L927

Next: implement a host-tested target frame allocation/conversion helper that checks dimensions and memory capacity, then integrate it into a separate Switch-target backend without modifying game logic. Validate regular frames and FMV frames independently.
