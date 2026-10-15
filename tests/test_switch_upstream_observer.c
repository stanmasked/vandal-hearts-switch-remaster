#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_upstream_observer.h"

static int uploads, draws, swaps;
static int permit_upload = 1;
static const uint8_t *seen;

static int viewport(void *context, int *w, int *h) {
    assert(context);
    *w = 1280; *h = 720;
    return 1;
}
static int swap(void *context) {
    assert(context);
    ++swaps;
    return 1;
}
int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p,
                                      const VhRgb24Frame *f) {
    assert(p && p->initialized);
    assert(f->width == 2 && f->height == 2 && f->stride_bytes == 6);
    seen = f->pixels;
    ++uploads;
    return permit_upload;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p, int w, int h) {
    assert(p && w == 1280 && h == 720);
    ++draws;
    return 1;
}

int main(void) {
    VhSwitchRgb24Presenter presenter = {0};
    int context = 1, other_context = 2;
    VhSwitchPresentHook hook = {&presenter, viewport, swap, &context};
    VhSwitchPresentHook other_hook = {&presenter, viewport, swap, &other_context};
    const uint8_t pixels[12] = {1,2,3,4,5,6,7,8,9,10,11,12};
    presenter.initialized = 1;
    { int w = -1, h = -1;
      assert(!vh_switch_observer_query_viewport(&w, &h));
      assert(w == -1 && h == -1); }
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 2, 2);
    assert(!vh_switch_observer_last_result() && uploads == 0 && swaps == 0);
    assert(!vh_switch_observer_register(NULL));
    assert(vh_switch_observer_register(&hook));
    { int w = 0, h = 0;
      assert(vh_switch_observer_query_viewport(&w, &h));
      assert(w == 1280 && h == 720);
      assert(!vh_switch_observer_query_viewport(NULL, &h)); }
    /* Registration is single-owner; a second hook must not replace the first. */
    assert(!vh_switch_observer_register(&hook));
    assert(!vh_switch_observer_register(&other_hook));
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 2, 2);
    assert(vh_switch_observer_last_result() == 1);
    assert(uploads == 1 && draws == 1 && swaps == 1 && seen == pixels);
    permit_upload = 0;
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 2, 2);
    assert(vh_switch_observer_last_result() == 0);
    assert(uploads == 2 && draws == 1 && swaps == 1);
    permit_upload = 1;
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels) - 1, 2, 2);
    assert(vh_switch_observer_last_result() == 0);
    assert(uploads == 2 && draws == 1 && swaps == 1);
    vh_switch_observer_unregister();
    { int w = -1, h = -1; assert(!vh_switch_observer_query_viewport(&w, &h)); }
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 2, 2);
    assert(!vh_switch_observer_last_result());
    assert(uploads == 2 && swaps == 1);
    /* The owner can be registered again after explicit teardown. */
    assert(vh_switch_observer_register(&other_hook));
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 2, 2);
    assert(vh_switch_observer_last_result() == 1);
    assert(uploads == 3 && swaps == 2);
    vh_switch_observer_unregister();
    puts("Upstream RGB24 observer binding tests passed.");
    return 0;
}
