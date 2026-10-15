# PC GPU observer integration gate

## Verified status (2026-10-15)

At GitHub Actions run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38770058367 the pinned upstream revision `14552fffa0e0b47e02b57592e274fc6e7a649923` was checked out, and `tools/patch_pc_gpu_present_observer.py` patched `platform/pc/src/pc_gpu_window.c` at the post-overlay, pre-desktop-present location. With `VH_SWITCH_COMPLETED_FRAME_OBSERVER` enabled, the resulting source compiled with SDL2 headers using strict C warnings; `source/switch_upstream_observer.c`, `source/switch_present_hook.c`, and the dependent frame modules compiled with GLES2 headers. Partial linking succeeded and `nm` verified that `VH_ObserveCompletedRGB24` was resolved in the resulting relocatable object.

### Current limitations

This is **host compilation and partial linking only**. Upstream unresolved platform and game symbols are permitted by relocatable linking; there is no full executable, no original game resource loading, no EGL/libnx context, no NeXium execution of the actual PC port and no physical Switch run. The opt-in observer currently runs in addition to the desktop present path: a registered callback which swaps frames will cause a second swap on the desktop path. Do not enable this callback for normal desktop gameplay without assigning exclusive present ownership. The target backend must replace the desktop submit/swap path when activated.

### Required next gate

1. Split or conditionally redirect the final desktop submit/swap so precisely one backend owns each frame.
2. Ensure the final `s_rgbaScratch` frame is passed only after FMV subtitle, OSD, and menu composition.
3. Provide target-owned current GLES2/EGL context, viewport query, buffer swap, and lifecycle handling.
4. Perform full target-side object linking and then a runtime smoke test with real game frames and legal locally supplied resources.

## Exclusive frame ownership gate (2026-10-15)

The observer patcher now supports an opt-in `VH_SWITCH_EXCLUSIVE_PRESENT` mode, guarded by `VH_SWITCH_COMPLETED_FRAME_OBSERVER`. Exclusive mode returns from `PC_GpuPresent` after the completed RGB24 frame callback so the desktop OpenGL draw and `SDL_GL_SwapWindow` path is skipped; without the exclusive define, normal desktop submission remains intact. Building exclusive mode without enabling the completed-frame callback raises a preprocessing error.

Passing CI: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38770570255 at commit `73e09cfd64cf5127b3f68a5ebb90a39945aa1b08`. The pinned upstream GPU translation unit compiled in default and exclusive modes, the missing-observer configuration failed as intended, and the exclusive output was partially linked with the observer and RGB24 bridge. Unit tests additionally assert that the return precedes SDL draw/swap.

**Scope:** desktop-host compile and partial link prove symbol compatibility and guard placement; they do not instantiate the Switch EGL context, run the game's frame loop, or prove real-frame rendering. Original `pc_gpu_window.c` still has SDL dependencies; a separate libnx target backend and runtime verification remain necessary.

## Switch NRO and NeXium observer runtime smoke gate

The resource-free NRO `upstream-rgb24-observer-probe.nro` initializes an SDL2 GLES2 context, constructs the RGB24 presenter, registers `VH_ObserveCompletedRGB24`, generates a synthetic moving RGB24 frame, and presents it through the target-owned viewport and SDL swap callbacks. CI build and NeXium runtime completed successfully: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38771695459 . The emulator screenshot was 1280×720, and its sampled center region contained 420 distinct colors. **This is an emulator smoke test for synthetic pixels, not original game frames or a physical Switch test.**

A stronger runtime gate was added in commit `817efe02`: capture two screenshots two seconds apart and require a substantial difference in their interior RGB pixels. This second gate must pass before claiming frame animation is runtime-verified. It cannot yet prove the displayed image is the original game; game data and the complete port are not linked into the NRO.

## Verified synthetic RGB channel orientation and motion (NeXium)

Run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38778923431 passed after adding four corner markers to the bottom-up RGB24 probe. Screen observations in CI were exact: top-left red (255,0,0), top-right green (0,255,0), bottom-left blue (0,0,255), bottom-right yellow (255,255,0); 1280×720 capture and 18,820 changed sampled pixels between two frames. This confirms **synthetic** RGB channel order and vertical orientation on the emulator path.

A further regression check in commit `590d942d` samples the synthetic center pixel across both frames: R=96 and G=93 must remain stable while the blue channel animates. It also checks all four corners on the second screenshot. Results remain pending until the associated workflow completes.

None of these tests verify output of original Vandal Hearts gameplay or textures. Next meaningful stage: bring legally available local upstream game frames into a separate target integration test, while keeping licensed assets outside the repository.

## Verified channel motion and forthcoming texture resize test (2026-10-15)

NeXium runtime run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38779397266 passed. The center pixel moved from RGB (96,93,138) to (96,93,245), while all four fixed corner markers retained their exact colors and screenshot orientation; the sampled viewport registered 18,820 changed pixels. This verifies RGB channel motion and orientation for synthetic frames on the SDL2/GLES2 observer path.

The observer NRO probe now also presents 320×240 and 4×3 synthetic RGB24 frames before its 9×7 animated sequence. This drives GLES2 texture allocation and resizing via the existing observer path, and aborts the probe if either upload/draw/swap call fails. The new run is not yet verified. Original Vandal Hearts game frames remain out of scope of this resource-free probe.

## Verified multi-resolution path and tightened state assertions

The synthetic observer NRO run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38779862674 completed successfully after submitting frames sized 320×240, 4×3, then 9×7 in NeXium. All RGB corner markers remained correct, animated center channels passed and 18,820 sampled pixels changed. The prior probe only checked return success and final screen rendering, not presenter's stored dimensions after the intermediate submissions.

Commit `802a423fa05fb3dbc14270a29d262f22091126af` adds explicit checks of `VhSwitchRgb24Presenter.frame_width/frame_height` after each synthetic resize. This checks the successful presenter upload path's size bookkeeping; it does **not** read back actual GPU texture storage. The new CI run must pass before the stronger assertion is considered verified.

## Presenter resize assertions confirmed; GLES2 framebuffer readback pending

Both NRO build and NeXium runtime jobs passed in https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38780267462 . The resource-free probe checked the presenter's dimensions on transitions 320×240 → 4×3 → 9×7; both jobs succeeded. This validates presenter state and successful submission but does not query actual GLES2 texture allocation sizes (OpenGL ES 2.0 does not offer desktop `glGetTexLevelParameteriv`).

Commit `c9a8d5cc425b513b0bdc09251580f5d31ec5d555` adds a runtime pixel readback before swap on the first two synthetic frames. The swap callback reads the drawable's center pixel with guaranteed GLES2 `glReadPixels(..., GL_RGBA, GL_UNSIGNED_BYTE)` and verifies (64,64,64) after the 320×240 upload and (192,192,192) after the 4×3 upload. An error prevents swap and fails the probe. This verifies *visible rendered content* after reallocation, not direct GPU storage dimensions. CI verification is pending.

## NeXium framebuffer readback verified; rejected-buffer runtime gate

Run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38781029048 passed its NRO build and NeXium runtime jobs, including the pre-swap GLES2 `glReadPixels` checks for gray synthetic frames after 320×240 and 4×3 texture uploads. The screenshot still showed expected corner markers and 18,820 changed sampled pixels. This is an actual framebuffer-content check, but still **not** a run of original game frames.

Commit `99b537c5ef0c9477e2387945d75188615b6351e7` strengthens the runtime probe: after a valid 4×3 RGB24 frame, it submits a one-byte-short buffer and asserts the observer fails without issuing a buffer swap or changing the stored frame dimensions. The swap callback counts completed swaps. This new gate is **pending CI validation**; previous host tests already covered invalid capacity.

## NeXium invalid-frame handling and target callback recovery (2026-10-15)

CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38781442357 passed build and NeXium runtime after the synthetic NRO submitted one RGB24 buffer whose declared capacity was one byte short. The C probe explicitly asserts that the observer rejects the submission, that its swap counter does not advance, and that the valid frame dimensions remain unchanged. The existing screenshot regression also passed.

Commit `61e321897e4b78fdb3b310f52be1a4a8c6ae28b6` extends the same NRO probe with one injected target swap failure, requiring failed observer status and no successful swap followed by recovery on the very next valid frame. Runtime CI confirmation is pending.

**Original PC renderer boundary:** Pinned `PC_GpuPresent` checks `s_window` and `s_glCtx` (or `s_renderer` on Apple) before compositing and pumps SDL events. Its injected completed-frame observer is an intermediate instrumented desktop translation unit, **not** a standalone headless or libnx graphics backend. A target-side platform initialization and event-loop adaptation are required before original game frames can drive the NRO.

## Injected-swap failure regression under investigation

The first NeXium runtime attempt at https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38783084428 failed screenshot validation twice, including after a retry of only the runtime job. Both builds succeeded, but the expected red upper-left marker was read as RGB (6,6,8). Thus the failure-injection recovery check from commit `61e32189` **is not validated**; no claim of runtime recovery is justified.

The original test injected failure before the animation loop. Commit `236dd094` moves injection to frame 90 of that loop, and emits reason-specific diagnostics for the failed return, missing swap suppression and recovery. Commit `f5cfa6d5` prints NeXium's capture log into the CI job before validating the screenshot. These are investigative changes; their result is pending. Existing green runs before the injection still establish synthetic frame display, resizing, color channel order and truncated-buffer rejection.

## Swap-recovery smoke and NeXium readiness stabilization

After moving the one-shot injected swap failure to frame 90, NeXium run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38786267027 **failed** the screenshot check (red marker reported as 6,6,8), while a subsequent run with the same probe code and extra logging, https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38786324953 , **passed**, showing all four correct RGB corner markers and 18,820 changed sample pixels. The contradictory outcomes are consistent with timing or launch sensitivity; do not conclude the earlier regression has been fully fixed by the probe modification alone.

Commit `db39cd18852fb1ba1b5c030406938831b15b3646` changes NeXium evidence capture from a fixed 20-second delay to polling for the actual expected red screen marker, with bounded retries and logged failure diagnostics. This is a readiness check before screenshot capture, not an attempt to hide failures. The corresponding CI run is pending. Further reliability runs are needed before marking swap failure recovery as stable.

## NeXium frame-ready polling confirmed

Run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38786879747 passed both NRO build and NeXium runtime with the injected swap-error/recovery check at frame 90. The screenshot harness waited for the actual upper-left red marker rather than capturing the emulator after a fixed delay; it reported "Observer RGB frame ready on poll 4". Subsequent screenshots matched the expected top-left (255,0,0), center red/green (96,93) with animated blue 56→148, and 18,820 changed sampled pixels.

This is one successful full run with readiness polling, following inconsistent runs with fixed-delay capture. It confirms that the improved harness can pass; it does not establish long-term reliability. The game itself remains unported to this NRO; the scene is synthetic.

## Reusable SDL2/GLES2 backend lifecycle module

The standalone `source/switch_sdl2_observer_backend.{h,c}` now owns SDL2 window, GLES2 context, RGB24 presenter, and observer registration lifetime as a single intermediate platform module. It only initializes the SDL video subsystem when it was not already active, and unregisters the observer before deleting its GL objects. `probes/sdl2_observer_backend_lifecycle.c` drives it with resource-free bottom-up RGB24 frames.

Build proof: https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38787816642 passed both builds including `sdl2-observer-lifecycle-probe.nro`. This proves an NRO could be built, **not** that its newly extracted lifecycle code rendered pixels.

Commit `61776dc2f96aaa8fbcc7e9b15afedadb56b49839` extends NeXium CI with a dedicated lifecycle NRO runtime screenshot and motion test, checking four RGB corner markers and animated blue channel. This separate run is pending. The screenshot test externally stops the emulator; it does not prove graceful guest shutdown or actual Vandal Hearts game-loop execution. The existing `PC_GpuPresent` still depends on desktop SDL state and remains a separate integration blocker.

## Reusable SDL2 observer backend runtime verification (NeXium)

Run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38788403755 completed successfully with both NROs built and both NeXium screenshot tests passing. The new reusable-lifecycle backend NRO reached a real RGB frame on polling attempt 4 and displayed the expected four corner markers (validated for both captures). Its center RGB transitioned from (108,92,96) to (108,92,197), proving continuing synthetic frame updates on the extracted SDL2/GLES2 lifecycle path. The original observer NRO also passed, showing 18,820 changed sampled pixels. This confirms image output from the refactored platform module, **not original Vandal Hearts gameplay**.

The lifecycle NRO is terminated externally by the emulator harness after the screenshots; graceful guest shutdown after a full session still requires its own exit assertion or device-level verification.

## Pinned upstream present callback without desktop window prerequisite (2026-10-15)

The pinned `PC_GpuPresent` implementation previously returned immediately when the desktop SDL window/GL context was missing, *before* RGB24 compositing and the optional observer seam. The patcher now guards that exact upstream window prerequisite with `#if !defined(VH_SWITCH_EXCLUSIVE_PRESENT)` while retaining the check unchanged in default desktop builds. The existing exclusive mode still returns immediately after the completed-frame observer callback to bypass desktop draw/swap, so there is one target presentation owner.

CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38789286600 passed against pinned upstream commit `14552fffa0e0b47e02b57592e274fc6e7a649923`: default desktop and exclusive translation units compiled with warnings-as-errors, the invalid exclusive-without-observer configuration was rejected, and the observer bridge partially linked. Source-level tests assert placement and reject mismatched desktop-guard anchors. Commits `98cca3d5` (patcher) and `f768876d` (tests).

**Scope limit:** this removes an *early window prerequisite*, not all desktop dependencies. The same source still pumps SDL events and relies on upstream game bootstrap, memory mappings, input, timing and existing overlay code. This is a host compile/partial-link test, not original gameplay executing in NeXium or on physical Switch.

## Observer callback ownership invariant

Before game-loop integration, the global `VH_ObserveCompletedRGB24` callback registry must have a single owner. Previously `vh_switch_observer_register` overwrote a live callback registration; destroying the first backend could then unregister a second backend with a dangling context/presenter. Commit `330c1b0c` refuses registration whenever an owner is already active, preserving the existing callbacks. Commit `669b573b` adds host regression tests for same-hook and competing-hook rejection, subsequent frame delivery, unregister and valid re-registration with a new context. CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38791389623 passed these RGB24 contract tests.

This is a lifecycle safety fix for later `PC_GpuPresent` integration, not evidence that the original game loop is running. The single-threaded observer registry does not synchronize multithreaded access; the future renderer must register on startup, present on the owning thread and unregister before destroying GL objects.

## SDL2 backend duplicate-initialization guard

The lifecycle module `switch_sdl2_observer_backend` now checks an already-live handle before clearing it or creating a new GL context. A second init on a live handle returns failure without overwriting the original window, context, presenter, or registered observer; callers must pass a zero-initialized structure for the first init. Commit `d360a7a0` added the guard, `c123aaa5` added a separate NeXium lifecycle-probe assertion that failed duplicate init preserves the original SDL window, GLES2 context and registered owner, and `1f7501f7` documented the initialization contract.

The unit-level single-observer owner tests passed in CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38791389623 and the pinned PC GPU seam compiled in https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38791437105. The **new** NRO lifecycle regression is pending runtime verification in https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38791692288 . Both graphics tests still use synthetic RGB24 frames, not original game rendering.

## Duplicate lifecycle init guard: NeXium verified

Run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38791692288 completed successfully for both NRO build and NeXium runtime, including `sdl2-observer-lifecycle-probe.nro` with an explicit second-init rejection and preserved active window/context/observer registration check. The subsequent live RGB24 rendering assertions passed: center RGB (108,92,227) → (108,92,60) with stable R/G channels, and the original observer probe still changed 18,820 sampled pixels. The lifecycle test continues to use synthetic frames and its teardown is executed by the guest only on its normal exit path; the emulator screenshot harness still terminates execution externally.

## Pinned PC_GpuPresent actual CPU conversion test (resource-free)

A host-only harness `tests/test_pinned_pc_gpu_present_rgb24.c` now links the **actual** `pc_gpu_window.c` at pinned upstream commit `14552fffa0e0b47e02b57592e274fc6e7a649923` after the project's optional observer patch. Unlike the Switch synthetic-pixel probe, this invokes `PC_GpuPresent` with deterministic 16-bit PS1/BGR555-like VRAM input. Its callback asserts the exact produced packed RGB24 bytes including 5-bit-to-8-bit channel replication and bottom-up row order. No user game data or bootstrapped game logic are involved.

CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38794088051 **passed** the first 3×2 full-frame case: `Pinned PC_GpuPresent delivered exact RGB24 colors and bottom-up row order.` The follow-up commit `2c4cceb8` adds a 5×3 source VRAM with 3×2 crop and nonzero x/y offsets to check source stride and viewport cropping; its CI result is **pending**.

The exclusive target observer patch also now skips `PC_GpuPumpEvents()` (commit `f908147d`). This is an intentional transfer of event pumping to the future outer Switch SDL2 event loop. Default desktop mode retains its original event pump; patcher tests enforce the conditional. Existing desktop window access and presentation remain unchanged outside opt-in exclusive mode.

This host harness proves an original upstream **conversion function**, not the native Switch game loop, original content, or physical console execution.

## Cropped VRAM read verified and observer-contract CI restored

Pinned upstream host run https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38794367702 passed both the original 3×2 BGR555→RGB24 check and the expanded 5×3-source/3×2-region test with nonzero x/y offsets, validating conversion, source VRAM stride, and bottom-up presentation by executing `PC_GpuPresent`. A Python test briefly failed because its expected preprocessor snippet used an escaped newline literal. Commit `dad3b4ec` removes that redundant fragile assertion; the comprehensive event-pump block test remains in place.

The corrected suite passed https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38794539930 (RGB24 frame handoff contract), and the pinned upstream compilation/conversion suite passed https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38794539814. This closes the host-only regression, but **does not yet verify execution of original `PC_GpuPresent` on Nintendo Switch or NeXium**. The next step is target compilation/linking and a platform-side game-loop and event-owner adapter; original game assets and bootstrap remain separate dependencies.

## Pinned original PC GPU module: initial devkitA64 cross-compilation

The patcher now guards the desktop-only `glDrawPixels/glPixelZoom/glRasterPos2f` presentation tail behind `!VH_SWITCH_EXCLUSIVE_PRESENT`, preserves the original desktop path by default and selects `SDL_opengles2.h` for the exclusive target configuration. The patched file still executes the upstream CPU VRAM→RGB24 conversion and synchronously invokes `VH_ObserveCompletedRGB24` before returning without the desktop swap. Exclusive builds explicitly mark unused desktop timing accumulators to pass warning-clean host builds. The patch only touches the pinned upstream source generated into the CI runner; no original game assets are committed.

A separate `pinned-gpu-switch-cross-compile.yml` workflow fetched pinned `HalmyLyseas/VandalHearts-PcPort` commit `14552fffa0e0b47e02b57592e274fc6e7a649923` and completed the first aarch64-none-elf object-only compilation successfully at https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38795978650. The later corrected host contract passed https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38796225648 and pinned GPU host compilation passed https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38796225848.

**Boundary:** cross-compiling a single object is not equivalent to linking it into a playable NRO. The original game's bootstrap and generated data, SDL input, movie/audio, save filesystem, rasterizer worker model and full game loop remain unported. The existing NeXium runtime screenshots use synthetic frames through the shared RGB24 observer, not the original upstream function in guest execution.

## Target GPU object dependency audit (verified)

CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38796516463 **passed** a pinned upstream `pc_gpu_window.c` compilation with devkitA64 (aarch64-none-elf), built with `-ffunction-sections -fdata-sections`. The workflow uploaded the compiled target object and `nm --undefined-only` inventory as `pinned-upstream-gpu-switch-object-audit`. It confirms the target object references `VH_ObserveCompletedRGB24`; importantly, the overall object does **not** list `glDrawPixels`, `glPixelZoom` or `glRasterPos2f` as unresolved symbols after suppressing the legacy desktop tail. A subsequent CI edit (commit `093317fd`) makes that absence an explicit gate, pending CI.

Other unresolved symbols **in the entire translation unit** include `PC_MovieSubsLoaded`, `PC_MovieSubsActive`, `PC_OverlayIsOpen`, several overlay and language-presentation accessors, `PC_BattleSpeedGet`, SDL window/event APIs, and normal C runtime calls. This `nm` inventory is conservative: dead sections may be removed by `--gc-sections` during a future link, so it must not be mistaken for the minimal runtime dependencies of `PC_GpuPresent` itself.

Next integration gate: link this original GPU object against `switch_sdl2_observer_backend.c`, the observer bridge and the minimal legitimate game-facing subsystems in a **resource-free synthetic VRAM NRO**. Avoid replacing game logic with permanent no-op stubs. Once that runs in NeXium and produces expected colors through the original `PC_GpuPresent`, tackle real game bootstrap, original-disc-dependent generated data and the input/audio/filesystem APIs separately. Physical Switch validation remains outstanding.

## First linked original PC_GpuPresent Switch NRO (2026-10-15)

CI https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/38799549787 **passed** full devkitA64 compilation, LTO/garbage-collected linking, elf2nro packaging and NRO0 segment validation of a new **resource-free integration executable** `build/upstream-cross/pinned-gpu-switch.nro`. The guest probe `probes/pinned_pc_gpu_switch_smoke.c` supplies generated 12×9 PS1 BGR555 VRAM pixels to the pinned upstream original `PC_GpuPresent`, which converts them into packed bottom-up RGB24 and calls `VH_ObserveCompletedRGB24`; this routes them through the project's actual Switch SDL2/GLES2 observer backend. The linked NRO file is 6,074,424 bytes. The workflow uploads `pinned-upstream-gpu-switch-nro`.

The linker uses temporary **probe-only stubs** for `PC_MovieSubsLoaded`, `PC_OverlayIsOpen`, and `PC_BattleSpeedGet` to keep real proprietary assets, game logic and full bootstrap out of this experiment; they must not be shipped as the game's implementations. The original conversion code is unchanged except for the opt-in platform presentation patch. This proves the code is in a genuine Switch NRO, **not yet that it executes or draws correctly under NeXium**.

Commit `7c401aca` extends the isolated GPU cross-compile workflow with a NeXium guest runtime job, RGB corner-marker/orientation checks, screenshot motion assertions, and evidence uploading. Guest runtime CI is pending.
