#ifndef VH_SWITCH_PRESENT_HOOK_H
#define VH_SWITCH_PRESENT_HOOK_H
#include "switch_completed_frame.h"

/* Viewport query and buffer swap are supplied by the target window layer. */
typedef int (*VhSwitchViewportQuery)(void *context, int *width, int *height);
typedef int (*VhSwitchSwapBuffers)(void *context);

typedef struct {
    VhSwitchRgb24Presenter *presenter;
    VhSwitchViewportQuery query_viewport;
    VhSwitchSwapBuffers swap_buffers;
    void *context;
} VhSwitchPresentHook;

/* Call once at the end of upstream compositing, not before overlay drawing.
 * Returns 0 on validation, upload/draw, viewport, or swap failure.
 * Synchronous: caller keeps pixels alive until return.
 */
int vh_switch_present_upstream_frame(const VhSwitchPresentHook *hook,
    const uint8_t *pixels, size_t actual_capacity, int width, int height);
#endif
