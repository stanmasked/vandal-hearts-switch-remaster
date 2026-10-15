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
