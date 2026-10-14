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

### Exact scratch-buffer contract: now confirmed

The frame-preparation code in `PC_GpuPresent` (around lines 780–820 at the audited revision) confirms:
- **Pixel format:** packed RGB24, in byte order R, G, B; there is no alpha byte in this scratch buffer. The variable name `s_rgbaScratch` is misleading.
- **Allocation:** `w * h * 3` bytes, grown when needed.
- **Row stride:** exactly `w * 3` bytes; rows are tightly packed, with no explicit per-row padding.
- **Orientation:** bottom-up. For source row `py`, the output row is `h - 1 - py`. The comments explicitly preserve this orientation for the GL raster path.
- **Color conversion:** each 16-bit VRAM pixel is interpreted as 5-bit red in bits 0–4, green in bits 5–9, and blue in bits 10–14. Each 5-bit channel expands to 8 bits by bit replication `(v << 3) | (v >> 2)`, mapping 31 to 255.
- **HD movie overlay:** the RGB24 movie path is already RGB triples; it copies each row into the same bottom-up scratch layout.
- **Post-processing:** subtitle covers/text and optional OSD/overlay are drawn into this same RGB24 buffer before presentation.
- **Presentation:** the desktop GL path supplies the buffer as `GL_RGB / GL_UNSIGNED_BYTE`; the Apple SDL texture path also declares RGB24 and explicitly flips vertically during copy.

These details define a much stronger adapter contract than the earlier name-only inference. The framebuffer pointer is only valid for the duration of the call unless a backend copies/uploads it before returning.

### Consequence

The clearest first graphics boundary is the final presentation of the CPU-rendered frame, not the software rasterizer itself. A Switch backend should accept the already-rendered pixels and upload/draw them with an API supported by the chosen Switch target. The existing GLES2 texture-upload probe is a plausible experiment, but it is not yet proven to preserve upstream pixel format, scaling, orientation, filtering, or frame pacing.

The desktop GL call uses `glDrawPixels` and `glPixelZoom`; these are not part of the OpenGL ES 2.0 API. Replace only this final presentation operation for the Switch path, rather than attempting to carry the desktop immediate/raster API across unchanged.

### Proposed implementation boundary

1. Keep the upstream software rasterizer and game logic untouched initially.
2. Define a frame contract: pointer, width, height, RGB24 format, tightly packed stride `width * 3`, bottom-up row order, and call-scoped lifetime.
3. Implement the Switch presenter as a separate platform-specific path, initially using the already-tested SDL2/GLES2 texture-upload route.
4. Upload as RGB data and account for row orientation explicitly: either retain the bottom-up data and flip texture coordinates, or flip rows once—not both.
5. Set/check the unpack alignment for RGB uploads. OpenGL texture uploads have row-alignment rules; RGB rows whose byte length is not divisible by the default alignment can be misread. The current native width of 320 gives a 960-byte row, but arbitrary-size movie frames need not.
6. Preserve the aspect-ratio letterbox calculation and nearest-neighbour intent; compare a captured known frame against the Switch presenter output for orientation, color channels, scaling, and black bars.
7. Retain the existing desktop path unchanged and rerun upstream's byte-matching check after any build integration.

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

The next implementation should be a small, independently testable presenter module or harness, not a patch to the upstream renderer yet. It should exercise a synthetic RGB24 frame with non-symmetric corner markers, a gradient, and widths that do and do not produce four-byte-aligned rows. That can catch orientation, channel order, and row-stride bugs before the adapter is wired into the upstream project.

Do not yet attempt to declare the whole upstream port Switch-compatible. The existing probes validate their own narrow behavior; they do not validate the original game framebuffer, its memory assumptions, full input API, audio, threads, or physical-console runtime.

## Evidence and limits

This document records source observations, not a successful upstream build or device test. Source locations refer to the audited upstream revision above. Re-check the source if the pinned upstream commit changes.

Relevant API reference: [OpenGL ES 2.0 reference pages](https://registry.khronos.org/OpenGL-Refpages/es2.0/xhtml/) and [texture upload row-alignment explanation](https://docs.gl/es2/glTexImage2D).

## 5. First host-side frame-contract test

Added `source/rgb24_frame.h` and `tests/test_rgb24_frame.c` on the isolated audit branch, and wired the test into the Makefile's `test` target.

The helper deliberately does not own or copy pixels. It validates the documented RGB24 dimensions/stride contract and exposes a top-down row accessor over the upstream bottom-up buffer. The unit test uses a 3-pixel-wide frame (9 bytes per row) with six distinct color markers, checks top/bottom row selection and RGB channel order, rejects out-of-range rows and invalid metadata, and confirms the expected 960-byte stride for a 320-pixel native frame.

**Confirmed locally:** the new test compiled with `gcc -std=c11 -Wall -Wextra -Werror -O2` and printed `RGB24 frame contract tests passed.`

**Important limitation:** the helper is a host-testable contract boundary, not yet called by the SDL2/GLES2 probe or the upstream game renderer. This verifies row interpretation and metadata validation only; it does not yet verify GPU texture upload, shader UVs, scaling, or emulator/console output.

## 6. Dedicated GLES2 RGB24 upload probe

Added `probes/rgb24_texture_smoke.c` and a `make rgb24-texture-probe` build target on this isolated branch. Unlike the existing gameplay-like texture probe, this one uploads a packed **RGB24** texture with dimensions **321×240** and a **963-byte row stride**, deliberately exercising rows that are not four-byte aligned.

The synthetic frame is stored bottom-up and has distinct red, green, blue, and yellow corner markers plus an interior gradient. The probe sets `GL_UNPACK_ALIGNMENT` to `1`, uploads with `GL_RGB / GL_UNSIGNED_BYTE`, uses nearest-neighbour filtering, and maps texture coordinates to preserve the bottom-up orientation. It logs the dimensions, stride, alignment, and immediate GL error code after upload.

**What this establishes:** there is now a dedicated, buildable-in-principle target for exercising the exact RGB24/GLES2 boundary, including the awkward row-stride case and orientation markers.

**Not yet confirmed:** this source has not yet been built with devkitPro, run in NeXium, or checked against a captured screenshot. A successful NRO build alone would not prove the colors and orientation are correct; the corner markers must be visually or automatically checked in the emulator. The original upstream renderer remains untouched.
