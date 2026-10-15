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


## Follow-up: concrete GLES2 integration seam

The isolated presenter has now passed the invalid-metadata recovery check in [run 38694397097](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38694397097). The next integration boundary is the final presentation block in `PC_GpuPresent()`: retain conversion, movie-frame handling, subtitles and OSD, and replace only the desktop GL raster calls for a dedicated Switch build. The implementation plan records the ES2 context setup, frame contract, upload/draw sequence, lifecycle ordering, and acceptance tests in [SWITCH_PRESENTER_INTEGRATION_PLAN.md](SWITCH_PRESENTER_INTEGRATION_PLAN.md).

The upstream source is still only audited, not modified or built for Switch. The Switch research repository does not contain the full upstream PC source tree; integration and physical-console validation remain open.


## 7. Bootstrap portability gate — follow-up source review (2026-10-15)

The pinned `platform/pc/src/pc_bootstrap.c` and `docs/pc-port/bootstrap.md` show that the bootstrap is more than fixed-address allocation:

- Startup constructor ordering reserves PSX memory, loads configuration, then performs bootstrap work including writable-data preparation, fault-handler setup, disc validation, and GPU initialisation.
- The code reserves 2 MiB at `0x80000000` and 1 KiB at `0x1f800000`; failure currently emits a warning and continues, even though direct-address game accesses can then fail later.
- POSIX builds include `sigaction`/signal-stack crash handling, x86-specific low-address read decoding, and `mprotect`-based writable-data retry. These are not portable abstractions that can be replaced wholesale by a Switch stub.
- The documented low-address-read emulation is limited to native i386. macOS, Windows, and the default Linux x86-64 path rely on source-level guards for these reads; unsupported accesses remain fatal.
- Bootstrap also derives deployment paths from the executable location and mounts a local disc image before opening the GPU window. Those path and media assumptions need a Switch-specific storage/configuration design.

### Required investigation before an upstream Switch build

1. Inventory every direct dereference of PSX RAM and Scratchpad addresses and identify the minimum memory ranges/aliasing semantics actually used by the selected region.
2. Determine whether Switch user-mode virtual memory can safely reserve those exact addresses. If it cannot, design a source-level address translation or backing-memory strategy; do not silently ignore reservation failure.
3. Inventory each fault-handler behavior separately. Do not port host signal handlers blindly, and do not disable them until their relevant recovery behavior has been proven unnecessary on the target.
4. Replace executable-relative disc/config discovery with an explicit Switch data root and report missing/invalid local data before GPU initialisation.
5. Only after those decisions, use a source-pinned, data-local build harness to expose compile/link errors. CI must not upload, cache, or package the user's disc image, BIOS/font source, or extracted game assets.

**Status:** this is a source-based risk inventory, not a Switch memory-layout validation or a compiled upstream patch. The current Switch repository still does not contain the full upstream source tree.


## 8. Existing `PC_PORT` memory seams — concrete follow-up (2026-10-15)

A targeted review of the pinned upstream source found that the codebase already contains narrow examples of replacing fixed PS1 addresses with ordinary backing storage. These are useful precedents, but they do **not** establish that all fixed-address dependencies have been removed:

- In `src/maps/unpack.c`, `UnpackMapFileData()` uses a static `u8 sPcScratchpad[0x400]` under `PC_PORT`; the non-`PC_PORT` path still assigns `pCache = (u8 *)0x1f800000`. The buffer is a 1 KiB dictionary ring, and its indexing is masked with `0x3ff`. This is a concrete, low-risk pattern to follow for other buffers when their lifetime and aliasing requirements are understood.
- In `src/core/cd.c`, the PC build maps the sound-work addresses such as `0x80140878`, `0x80141878`, and `0x80144878` through `SOUND_WORK_PTR(addr)` into `sPcSoundWorkRam`, instead of directly returning the numeric address. This is a second precedent for a source-level backing-memory mapping.
- These examples differ in scope: the map unpacker has a single local scratch ring, while the sound-work table maps multiple offsets into a shared region. They must not be generalized into one global address translation until all consumers, offsets, sizes, and alias relationships are inventoried.

### Updated implementation gate

Before modifying the upstream bootstrap, build an address-use inventory from the pinned source with at least these columns: source file/line, literal or base address, read/write use, required size, lifetime, alias group, existing `PC_PORT` guard, and candidate backing store. Include direct casts, arithmetic based on PS1 addresses, and buffers whose address is stored in tables—not just grep hits for the two base constants.

**Decision:** prefer explicit source-level backing buffers for each verified memory region over attempting to reserve PS1 virtual addresses on Switch. Keep exact-address reservation only as a separately tested fallback if the target demonstrably supports it. The two examples above justify investigating this strategy; they are not yet evidence that the full game can run with relocated RAM.

**Status:** source review only. No upstream source was copied into this repository, no game data was accessed, and no Switch memory mapping or upstream build was performed.


## 9. Initial fixed-address inventory (2026-10-15)

This is the first concrete inventory slice from the pinned upstream revision `14552fffa0e0b47e02b57592e274fc6e7a649923`. It intentionally distinguishes confirmed source facts from information that still needs a whole-tree audit.

| Region / seam | Source location | Current behavior | Size / aliasing | Switch implication |
| --- | --- | --- | --- | --- |
| PSX main RAM | `platform/pc/src/pc_bootstrap.c`, `PSX_RAM_BASE` | Attempts to reserve `0x80000000` for 2 MiB; game code may directly dereference addresses in this range | 2 MiB reservation; exact subrange and aliases are not fully inventoried | Do not treat reservation failure as harmless; map direct users before choosing a replacement |
| PSX scratchpad | `platform/pc/src/pc_bootstrap.c`, `PSX_SCRATCHPAD_BASE` | Attempts to reserve `0x1f800000` for 1 KiB | 1 KiB nominal range; at least one consumer has an existing PC fallback | Use the existing per-consumer fallback pattern only after verifying all scratchpad users |
| Map decompressor dictionary | `src/maps/unpack.c`, `UnpackMapFileData()` | Under `PC_PORT`, uses static `sPcScratchpad[0x400]`; otherwise uses `0x1f800000` | 1 KiB ring; dictionary indexing wraps with mask `0x3ff` | Good example for a scoped backing store; not evidence that other scratchpad uses are equivalent |
| Sound-work RAM | `src/core/cd.c`, `SOUND_WORK_PTR(addr)` | PC branch maps known PS1 sound-work addresses into `sPcSoundWorkRam` | Multiple offsets share a backing region; complete consumer extent and overlap must be confirmed | Preserve offsets/aliasing; do not replace each address with unrelated arrays |
| Writable-data compatibility | `platform/pc/src/pc_bootstrap.c` | Desktop-specific section permission changes / write retry are used | Depends on host loader and section layout | Exclude desktop permission hacks from Switch until each behavior has a demonstrated requirement |
| Low-address read compatibility | `platform/pc/src/pc_bootstrap.c` | Host-specific fault/read handling includes architecture guards | Not a general memory abstraction | Do not port signal-handler or x86-specific decoding paths as a generic Switch layer |

### Inventory completion criteria

This table is a starting slice, not a completed memory map. The next pass must search all game and platform translation units for (a) casts from integer constants to pointers, (b) arithmetic from RAM base macros, (c) pointer values embedded in tables, and (d) assembly or generated code that assumes the original address layout. For each hit, record the required byte range, read/write behavior, object lifetime, and whether the PC branch already supplies a replacement.

The implementation remains blocked until the table covers the complete selected-region source set and tests demonstrate that any proposed backing regions preserve overlap and pointer arithmetic. No Switch runtime address assumptions are made in this document.


## 10. Map decompressor scratchpad access — pinned-source verification (2026-10-15)

A direct read of `src/maps/unpack.c` at upstream revision `14552fffa0e0b47e02b57592e274fc6e7a649923` confirms these implementation details:

- `UnpackMapFileData(u8 *input, u8 *output, s32 len)` selects `static u8 sPcScratchpad[0x400]` under `PC_PORT`; the non-PC branch casts `0x1f800000` to a byte pointer.
- The function clears indices `0..989` and starts `cacheOfs` at `990`; writes and back-references wrap with `& 0x3ff`. The entire 1024-byte array is addressable, even though only 990 bytes are explicitly cleared at entry.
- `ProcessMapFileData()` reads a four-byte little-endian compressed length and passes `&input[4]` plus the global `gMapDataPtr` as output. Thus the scratch ring is local to decompression, but the output storage is a separate global whose allocation, capacity and lifetime still require auditing.
- The source has no output-capacity parameter for `UnpackMapFileData()`. Its existing contract therefore does **not** prove bounds safety for malformed or truncated map data; a Switch-facing loader should validate the input/output allocation contract before calling it, without changing original decompression semantics prematurely.

**Alias classification:** the `PC_PORT` dictionary is one static function-scoped backing array, distinct from `gMapDataPtr`. The pinned function does not itself demonstrate aliasing with the full PS1 scratchpad region; other consumers must be searched before generalizing. No runtime or memory-safety test is claimed for this source review.


## 11. `gMapDataPtr` declaration and unresolved ownership (2026-10-15)

At pinned upstream revision `14552fffa0e0b47e02b57592e274fc6e7a649923`, `include/field.h` declares `extern u8 *gMapDataPtr;`. In `src/maps/unpack.c`, `ProcessMapFileData()` passes that pointer directly to `UnpackMapFileData()` as the output destination. A targeted inspection of `src/maps/common.c`, `src/battle/field.c`, `src/events/scene_loaders.c`, and `src/core/cd.c` did not find the symbol; this limited check is **not** a whole-tree proof of absence.

**Open ownership questions:** locate the pointer definition and all assignments; determine its allocation base, capacity, initialization and reset sequence, whether it aliases PS1 RAM or another map buffer, and the maximum decompressed size for every supported map. Confirm whether compressed input length and output capacity are validated by callers. A pointer declaration alone establishes none of these properties.

**Switch integration gate:** do not wrap the existing decompressor with an invented output size or assume the map's dimensions imply byte capacity. First trace ownership and format bounds from actual source and local test fixtures. No original game assets or runtime tests were used in this review.


## 12. Map output alias discovered in pinned game source (2026-10-15)

The map-output pointer has a concrete assignment: `src/core/main.c:272` sets `gMapDataPtr = gScratch3_80180210`. `include/common.h:139` declares the underlying `extern u8 gScratch3_80180210[]` **without a bound**. Consequently, neither declaration establishes the actual allocation size.

This backing region is shared rather than map-only: `src/core/main.c:66` and `:85` assign `gUnitDataPtr = gScratch3_80180210 + 0x2db80`. `src/states/game_setup.c` also reads texture/portrait data at offsets including `0x8000`, `0x10000`, `0x18000`, and `0x20000`, and builds `gMapRowPointers` from `gMapDataPtr` with multiple `MapTileModel` row strides (including 14, 28, 48, and 64). These uses are not necessarily simultaneous; their lifetimes and overlap must be traced before choosing storage ownership.

The same `game_setup.c` calls `ProcessMapFileData(&gScratch1_801317c0[0])` (near line 2592), so compressed input and decompressed output originate from **different named scratch regions**. `src/core/main.c:67-69` also derives save-data pointers from `gScratch1_801317c0` at offsets `0x5000`, `0x6000`, and `0xa000`. The size, definition, and lifetime of both scratch arrays remain unresolved.

**Next evidence gate:** find actual definitions and capacities of `gScratch3_80180210` and `gScratch1_801317c0`; map every live alias and loading phase; check decompressed byte limits before replacing the shared region. Do not infer capacity from the largest observed offset or a row stride. This is source inspection only, not a runtime bounds proof.


## 13. Targeted scratch-buffer definition check (2026-10-15)

A second pass over pinned `src/core/main.c`, `src/core/engine.c`, `src/states/game_setup.c`, and `platform/pc/src/pc_bootstrap.c` found usages but **no storage definitions** of `gScratch1_801317c0` or `gScratch3_80180210` in those four files. `include/common.h` exposes unsized `extern u8` declarations. This is a **negative result limited to these inspected files**, not a repository-wide search.

The known alias offsets remain: scratch3 base (`gMapDataPtr`), scratch3 + `0x2db80` (`gUnitDataPtr`), and scratch1 + `0x5000`/`0x6000`/`0xa000` (save/card pointers). The largest referenced offset is **not** evidence of the backing allocation size. The next search must cover the selected-region global data objects, assembly/linker-generated symbols, and PC compatibility definitions, not only C translation units. Determine whether the two names denote separately allocated arrays, linker-address aliases, or mapped portions of a larger emulated memory range before implementation.

**No source or binary integration performed.** The Switch memory ownership model remains open pending symbol-definition evidence.


## 14. Linker-symbol addresses and map-specific alias (2026-10-15)

Pinned upstream `symbol_addrs.txt` gives **addresses, not allocation sizes**: `gScratch1_801317c0 = 0x801317c0` (line 1652) and `gScratch3_80180210 = 0x80180210` (line 1701). These are addresses in the original PS1 layout and must **not** be cast directly into valid pointers on Nintendo Switch. `include/common.h` still declares both as unsized byte arrays, so the available capacity remains unproven.

A previously missed alias appears in `src/units/load.c:140-142`: when `gState.mapNum == 39`, `gUnitDataPtr` becomes `gScratch3_80180210 + 0x3a300`; otherwise it uses `+ 0x2db80`. The destination pointer therefore has at least two map-dependent offsets, and a single constant partition would be incorrect without checking its users, extent and loading phase.

Additional scratch1 aliases are initialized directly in `src/core/card.c:623-626`: `gCardFilenameBufferPtr = gScratch1_801317c0`, `gCardFileBufferPtr = &gScratch1_801317c0[64]`, and `gCardFileVerifyBufferPtr = &gScratch1_801317c0[8256]`. These coexist with the scratch1 offsets `0x5000`, `0x6000` and `0xa000` recorded in section 12. As with the scratch3 offsets, offsets alone are **not** evidence for object sizes or concurrent validity.

**Implementation constraint:** inventory PS1-symbol definitions and linker/PC-port mapping separately from C references. Before implementing region translation, trace map 39 data loading, file-size assumptions, buffer lifetimes, and whether scratch1/scratch3 are portions of the same backing PS1 RAM. Do not allocate just up to the highest referenced offset, and do not assume the PS1 addresses are usable as Switch virtual addresses. This is a pinned-source finding, not a measured memory-safety result.


## 15. PC fixed-address reservation versus Switch backing policy (2026-10-15)

Pinned `platform/pc/src/pc_bootstrap.c:39-111` gives the precise desktop boundary:

- `PSX_RAM_BASE` is `0x80000000UL`, `PSX_RAM_SIZE` is `2 * 1024 * 1024`; `PSX_SCRATCHPAD_BASE` is `0x1f800000UL`, and the scratchpad size is `0x400`.
- The Windows branch of `ReservePsxMemory()` uses `VirtualAlloc(base, size, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE)` and rejects a NULL or relocated result. The non-Windows, non-Apple POSIX branch uses anonymous private `mmap(..., MAP_FIXED_NOREPLACE, ...)` and likewise expects the exact base.
- Despite returning failure from `ReservePsxMemory()`, `PC_ReservePsxRam()` ignores the result of both reservation calls; source comments warn that direct fixed-address consumers may crash later. This is **not** acceptable as a silent fallback when making a Switch memory design.
- Under `__APPLE__`, the fixed reservation calls are skipped; the source comment specifically notes arm64 Mach-O low-address constraints and PC-backed work buffers. This is evidence of a platform-specific strategy, **not** evidence that every fixed-address dereference has been converted or that libnx supports identical mapping.
- The PS1 KUSEG zero-address mirror is explicitly *not* mapped by this PC bootstrap. Fault emulation is limited to defined host cases; it does not provide general-purpose PS1 address translation.

**Switch design gate:** retain the symbolic PS1 offsets as metadata, identify live aliases and size boundaries, and implement explicit backing storage for verified consumers. Any remaining raw numerical PS1 address cast must be enumerated and adapted or shown safe in a target-specific test; do not assume successful allocation at `0x80000000` on libnx. Make allocation failure fatal at the subsystem boundary, and do not adopt platform-specific signal/VM fault handlers without independent target evidence. Source review only; no libnx memory API test or original game runtime validation has been performed.
