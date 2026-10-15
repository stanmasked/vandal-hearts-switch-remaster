#ifndef VH_SWITCH_UPSTREAM_OBSERVER_H
#define VH_SWITCH_UPSTREAM_OBSERVER_H
#include "switch_present_hook.h"

/*
 * Install a copy of the target callbacks before frames are presented.
 * Presenter and context objects must outlive registration.
 * Single-threaded rendering only; unregister before destroying the context.
 * Only one owner may be registered at a time. Duplicate registration fails
 * without replacing the active callbacks; unregister before re-registering.
 */
int vh_switch_observer_register(const VhSwitchPresentHook *hook);
void vh_switch_observer_unregister(void);
int vh_switch_observer_last_result(void);

/* Exact symbol expected by the opt-in upstream PC_GpuPresent patch. */
void VH_ObserveCompletedRGB24(const unsigned char *pixels,
                              size_t capacity, int width, int height);
#endif
