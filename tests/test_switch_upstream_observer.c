#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_upstream_observer.h"

static int uploads, draws, swaps, queries;
static int allow_swap = 1;
static int allow_viewport = 1;

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p, const VhRgb24Frame *f) {
    assert(p && p->initialized && f && f->width == 2 && f->height == 2);
    ++uploads;
    return 1;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p, int w, int h) {
    assert(p && w == 1280 && h == 720);
    ++draws;
    return 1;
}
static int query(void *ctx, int *w, int *h) {
    assert(ctx);
    ++queries;
    *w = 1280; *h = 720;
    return allow_viewport;
}
static int swap(void *ctx) {
    assert(ctx);
    ++swaps;
    return allow_swap;
}
int main(void) {
    uint8_t rgb[12] = {0};
    VhSwitchRgb24Presenter presenter;
    int context = 7;
    VhSwitchPresentHook hook;
    memset(&presenter, 0, sizeof(presenter));
    memset(&hook, 0, sizeof(hook));
    presenter.initialized = 1;
    hook.presenter = &presenter;
    hook.context = &context;
    hook.query_viewport = query;
    hook.swap_buffers = swap;

    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(!vh_switch_observer_last_result() && !uploads && !swaps);
    assert(!vh_switch_observer_register(NULL));
    assert(vh_switch_observer_register(&hook));
    assert(!vh_switch_observer_register(&hook));
    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(vh_switch_observer_last_result());
    assert(queries == 1 && uploads == 1 && draws == 1 && swaps == 1);

    VH_ObserveCompletedRGB24(rgb, sizeof(rgb) - 1, 2, 2);
    assert(!vh_switch_observer_last_result());
    assert(queries == 1 && uploads == 1 && swaps == 1);

    allow_swap = 0;
    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(!vh_switch_observer_last_result());
    assert(uploads == 2 && draws == 2 && swaps == 2);

    /* A viewport failure must not upload, draw or swap. */
    allow_swap = 1;
    allow_viewport = 0;
    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(!vh_switch_observer_last_result());
    assert(queries == 3 && uploads == 2 && draws == 2 && swaps == 2);
    allow_viewport = 1;

    vh_switch_observer_unregister();
    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(!vh_switch_observer_last_result());
    assert(uploads == 2 && draws == 2 && swaps == 2);
    vh_switch_observer_unregister();
    /* Explicit teardown allows a new owner to register cleanly. */
    assert(vh_switch_observer_register(&hook));
    VH_ObserveCompletedRGB24(rgb, sizeof(rgb), 2, 2);
    assert(vh_switch_observer_last_result());
    assert(queries == 4 && uploads == 3 && draws == 3 && swaps == 3);
    vh_switch_observer_unregister();
    assert(!vh_switch_observer_last_result());
    puts("Upstream observer registration tests passed.");
    return 0;
}
