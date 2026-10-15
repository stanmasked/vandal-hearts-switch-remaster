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
