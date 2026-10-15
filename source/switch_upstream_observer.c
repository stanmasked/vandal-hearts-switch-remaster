#include "switch_upstream_observer.h"

static VhSwitchPresentHook active_hook;
static int registered;
static int last_result;

int vh_switch_observer_register(const VhSwitchPresentHook *hook) {
    if (registered || !hook || !hook->presenter || !hook->query_viewport || !hook->swap_buffers)
        return 0;
    active_hook = *hook;
    registered = 1;
    last_result = 0;
    return 1;
}

void vh_switch_observer_unregister(void) {
    active_hook.presenter = 0;
    active_hook.query_viewport = 0;
    active_hook.swap_buffers = 0;
    active_hook.context = 0;
    registered = 0;
    last_result = 0;
}

int vh_switch_observer_last_result(void) {
    return last_result;
}

void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                              size_t capacity, int width, int height) {
    last_result = registered
        ? vh_switch_present_upstream_frame(&active_hook,
                                           pixels, capacity, width, height)
        : 0;
}
