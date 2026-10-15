#include "switch_upstream_observer.h"

static VhSwitchPresentHook s_hook;
static int s_registered;
static int s_last_result;

int vh_switch_observer_register(const VhSwitchPresentHook *hook) {
    if (!hook || !hook->presenter || !hook->presenter->initialized ||
        !hook->query_viewport || !hook->swap_buffers)
        return 0;
    /* Reject duplicate registration until the owner explicitly unregisters. */
    if (s_registered)
        return 0;
    s_hook = *hook;
    s_registered = 1;
    s_last_result = 0;
    return 1;
}

void vh_switch_observer_unregister(void) {
    VhSwitchPresentHook empty = {0};
    s_hook = empty;
    s_registered = 0;
    s_last_result = 0;
}

int vh_switch_observer_last_result(void) {
    return s_last_result;
}

void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                              size_t capacity, int width, int height) {
    if (!s_registered) {
        s_last_result = 0;
        return;
    }
    s_last_result = vh_switch_present_upstream_frame(
        &s_hook, pixels, capacity, width, height);
}
