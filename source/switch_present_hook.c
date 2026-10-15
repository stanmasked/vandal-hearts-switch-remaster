#include "switch_present_hook.h"
#include "frame_conversion.h"

int vh_switch_present_upstream_frame(const VhSwitchPresentHook *hook,
    const uint8_t *pixels, size_t actual_capacity, int width, int height) {
    int viewport_width, viewport_height;
    size_t required;
    if (!hook || !hook->presenter || !hook->presenter->initialized ||
        !hook->query_viewport || !hook->swap_buffers || !pixels ||
        !vh_rgb24_required(width, height, &required) ||
        actual_capacity < required)
        return 0;
    viewport_width = viewport_height = 0;
    if (!hook->query_viewport(hook->context, &viewport_width, &viewport_height) ||
        viewport_width <= 0 || viewport_height <= 0)
        return 0;
    if (!vh_switch_present_completed_rgb24(hook->presenter, pixels,
            actual_capacity, width, height, viewport_width, viewport_height))
        return 0;
    return hook->swap_buffers(hook->context) ? 1 : 0;
}
