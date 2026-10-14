# Upstream presentation and bootstrap source audit

**Audit target:** `HalmyLyseas/VandalHearts-PcPort` at commit `14552fffa0e0b47e02b57592e274fc6e7a649923`.
**Method:** read-only inspection of upstream source through GitHub. No upstream or game source was changed.

## 1. Presentation path: confirmed incompatibility seam

File: `platform/pc/src/pc_gpu_window.c` (audited blob SHA `47bc26af6134e70d7f307a560ef1a4a5a287aab3`).

Relevant source locations:
- Around lines 598 and 707, the PC window uses a 320x240 native game framebuffer multiplied by a desktop scale factor.
- Around line 864, the code scales the native framebuffer to the viewport while preserving aspect ratio.
- Around lines 906–908, the desktop OpenGL path uses `glPixelZoom`, `glRasterPos2f`, and `glDrawPixels(w, h, GL_RGB, GL_UNSIGNED_BYTE, s_rgbaScratch)`.
- Around lines 913–915, presentation branches to `SDL_RenderPresent` for SDL renderer mode or `SDL_GL_SwapWindow` for the desktop GL window.

### Consequence

The clearest first graphics boundary is the final presentation of the CPU-rendered frame, not the software rasterizer itself. A Switch backend should accept the already-rendered pixels and upload/draw them with an API supported by the chosen Switch target. The existing GLES2 texture-upload probe is a plausible experiment, but it is not yet proven to preserve upstream pixel format, scaling, orientation, filtering, or frame pacing.

Important data-contract detail: the audited call passes `GL_RGB` and `GL_UNSIGNED_BYTE` with a buffer named `s_rgbaScratch`. Do not assume the name proves four-channel RGBA storage; inspect allocation, row stride, conversion, and pixel-store state before designing an upload adapter. Record whether alpha exists, the exact bytes per pixel, and whether rows are top-down or bottom-up.

### Proposed implementation boundary

1. Keep the upstream software rasterizer and game logic untouched initially.
2. Identify the exact buffer preparation immediately before the presentation calls.
3. Define an adapter contract containing pointer, width, height, pixel format, and row stride (or document why stride is implicit).
4. Implement the Switch presenter as a separate platform-specific path, initially using the already-tested SDL2/GLES2 texture upload route.
5. Compare a captured upstream desktop frame with the Switch presenter output using a known test frame; check orientation, RGB/RGBA interpretation, row alignment, scaling, and letterboxing.
6. Retain the existing desktop path unchanged and rerun upstream's byte-matching check after any build integration.

## 2. Input path: adapter needed

File: `platform/pc/src/libetc.c` (audited blob SHA `8d0c7a01e212ce6c0c10f984b18f1e30d84e4d88`).

Confirmed source features:
- Optional controller state is held in `SDL_GameController *s_pad`.
- The code opens a controller using `SDL_GameControllerOpen`, checks attachment, reads mapped buttons/axes, and combines them with keyboard state.
- The keyboard path uses `SDL_GetKeyboardState` (around line 194).

The Switch SDL2 probe already demonstrates joystick-event input in NeXium, but this does not prove the upstream `SDL_GameController` code works with Switch controllers. The first input implementation should isolate polling/event translation behind a small adapter and preserve the PS1 digital-pad bitmask contract expected by the game-facing API. Validate button mapping, axes, repeat/edge behavior, hotplug assumptions, and cancellation separately.

## 3. Bootstrap: high-risk, not a window-only port

File: `platform/pc/src/pc_bootstrap.c` (audited blob SHA `1020af186761cd323e88d94da21c8755a093cdd9`).

Confirmed platform-specific assumptions include:
- Windows headers and `VirtualAlloc` for fixed-address reservations (around lines 13–68).
- POSIX `mmap` and `mprotect` for memory mappings/protection (around lines 75 onward and 553/676).
- macOS Mach-O and dyld inspection via `mach-o/dyld.h`, `mach-o/loader.h`, `_dyld_get_image_header`, and `_dyld_get_image_vmaddr_slide` (around lines 29 and 722–723).
- A later executable-memory/protection path calls `VirtualProtect` (around line 701).

These are not interchangeable convenience wrappers: the bootstrap accommodates the original game's memory/executable assumptions. Do not replace them with no-op stubs just to get a compile. For each path, determine whether it is needed on Switch, what address/range and permission behavior the game expects, and whether the Switch process model supports a safe equivalent. This requires a dedicated memory-layout review before linking the full game.

## 4. Dependency and sequencing conclusion

Recommended first integration target: **a standalone presentation adapter with a documented frame contract**, while continuing the bootstrap and input inventories in parallel as read-only analysis.

Do not yet attempt to declare the whole upstream port Switch-compatible. The existing probes validate their own narrow behavior; they do not validate the original game framebuffer, its memory assumptions, full input API, audio, threads, or physical-console runtime.

## Evidence and limits

This document records source observations, not a successful upstream build or device test. Source locations refer to the audited upstream revision above. Re-check the source if the pinned upstream commit changes.
