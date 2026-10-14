# Switch porting API inventory

**Status:** planning inventory based on the upstream audit at commit [14552fffa0e0b47e02b57592e274fc6e7a649923](https://github.com/HalmyLyseas/VandalHearts-PcPort/commit/14552fffa0e0b47e02b57592e274fc6e7a649923). This is not a claim that any upstream subsystem has been ported.

## Priority order

| Priority | Subsystem | Desktop assumption / risk | Switch-side direction | Evidence required before marking done |
| --- | --- | --- | --- | --- |
| P0 | Build and generated data | Upstream build has generated files that depend on user-supplied original executable and PsyQ `KROMDAT.BIN` or compatible BIOS font source. | Keep generation local; document tools and inputs without checking proprietary files into Git. | Reproducible build steps and hashes for generated outputs that are safe to record; no proprietary assets in repository or CI artifacts. |
| P1 | Frame presentation | PC renderer uses legacy desktop OpenGL calls including `glPixelZoom`, `glRasterPos2f`, and `glDrawPixels`; these are not GLES2 APIs. | Introduce a small presentation interface that consumes a known RGBA framebuffer; initially implement a GLES2 texture-upload/fullscreen-quad backend or libnx framebuffer backend. | Compare pixel format, stride, orientation, scaling, palette/alpha handling against upstream output; verify in emulator and physical hardware. |
| P1 | Input | Desktop input polls SDL keyboard state and optional SDL game-controller APIs. Switch SDL2 input behavior may expose buttons through joystick events. | Isolate game actions behind an adapter; map Switch pad buttons to directional movement, confirm, cancel, and exit. | Automated transition tests, emulator interaction checks, then physical Joy-Con/Pro Controller tests. |
| P2 | Bootstrap and memory | `pc_bootstrap.c` has Windows `VirtualAlloc`/`VirtualProtect`, POSIX `mmap`/`mprotect` and ELF handling, and macOS Mach-O/dyld branches. | Audit every allocation/protection/image-inspection behavior; do not replace APIs mechanically until the original memory assumptions are understood. | Per-function requirements, target-specific implementation, and tests for allocation bounds, permissions, and failure cleanup. |
| P2 | Audio | Desktop backend uses OpenAL; availability on Switch and audible output are not established. SDL2 audio test is currently blocked by missing CI ALSA device; OpenAL package installs have seen HTTP 403. | Keep audio behind an interface; compare a minimal SDL2 audio path and OpenAL only when package installation is available. | Successful NRO build plus runtime callback/state evidence; audible output in a supported emulator and physical hardware tested separately. |
| P2 | Threading and rasterizer worker pool | High-resolution rasterizer uses pthread worker threads. | First determine whether baseline rendering needs threads; only port the worker pool after single-threaded correctness and device profiling. | Thread lifecycle/synchronization tests, repeated stress run, and measured performance on target hardware. |
| P3 | HD background packs | Optional WebP support adds libwebp and memory/decoding overhead. | Disable optional HD pack path for initial baseline; reintroduce only after baseline gameplay and memory budget are stable. | Separate dependency/build test, image-decoding correctness, memory/performance measurements. |
| P3 | HD movies | Optional movie replacement path uses FFmpeg/libav components. | Keep disabled for initial baseline; decide later whether native video playback or replacement assets are worth the dependency cost. | Codec/dependency feasibility, file access, sync and performance tests on device. |
| P3 | Filesystem and disc access | Upstream expects user-provided disc data at runtime and uses local generation inputs. | Keep user-supplied files outside source control; design a clear user-selected data path and fail safely for missing/invalid data. | Generated-file smoke test, path/permission handling, malformed/missing file tests; no proprietary data in CI. |

## Porting boundary

Do not port the decompiled game logic first. Start by defining a narrow platform seam for:

1. framebuffer presentation;
2. input actions;
3. timing and frame pacing;
4. audio output;
5. file/data access;
6. memory/bootstrap behavior.

The existing standalone prototype only demonstrates that the selected toolchain can build a minimal NRO and that generated grid/input interactions work in NeXium. It does **not** demonstrate that upstream game code or its PC platform layer compiles or runs on Switch.

## Current blockers and known evidence

- The main libnx prototype has passed NeXium movement/selection/cancel/invalid-move smoke checks documented in [the prototype checklist](PROTOTYPE_CHECKLIST.md).
- SDL2 software-renderer, GLES2-context, and framebuffer-texture probes previously passed NeXium screenshot/input checks. The current rerun is blocked before compilation by HTTP 403 errors retrieving devkitPro package databases; see [audio probe results](AUDIO_PROBE_RESULTS.md) and [workflow run 38610973016](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38610973016).
- Audio callback execution is not the same as audible output. Physical-console graphics, controller, audio, and long-session checks remain open.
- Upstream rights are mixed: the PC-port code is identified as GPL-2.0, while the upstream notice excludes decompiled game code and game-derived data from that grant. Review the upstream license and notices before copying any files; do not commit disc images, executables, BIOS/SDK data, extracted assets, or generated copyrighted content.

## Completion rule

For each subsystem, record: exact upstream revision, changed files, build command, toolchain/library versions, automated test, runtime environment, artifact/log link, and unresolved limitations. Mark a milestone complete only when its own evidence exists; a successful compile cannot substitute for runtime validation.
