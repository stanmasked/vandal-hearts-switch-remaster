#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_present_hook.h"

typedef struct {
    int queries, uploads, draws, swaps;
    int query_ok, upload_ok, draw_ok, swap_ok;
    const uint8_t *seen;
} Trace;

static Trace trace = {0,0,0,0,1,1,1,1,NULL};

static int query_viewport(void *ctx, int *width, int *height) {
    Trace *t = (Trace *)ctx;
    ++t->queries;
    if (!t->query_ok) return 0;
    *width = 1280; *height = 720;
    return 1;
}
static int swap_buffers(void *ctx) {
    Trace *t = (Trace *)ctx;
    ++t->swaps;
    return t->swap_ok;
}
int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p,
                                     const VhRgb24Frame *f) {
    assert(p && p->initialized);
    assert(f->width == 2 && f->height == 2 && f->stride_bytes == 6);
    trace.seen = f->pixels;
    ++trace.uploads;
    return trace.upload_ok;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p, int w, int h) {
    assert(p && w == 1280 && h == 720);
    ++trace.draws;
    return trace.draw_ok;
}
int main(void) {
    VhSwitchRgb24Presenter presenter = {0};
    uint8_t frame[12] = {1,2,3,4,5,6,7,8,9,10,11,12};
    VhSwitchPresentHook hook = {&presenter, query_viewport, swap_buffers, &trace};
    presenter.initialized = 1;
    assert(vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 2, 2));
    assert(trace.queries == 1 && trace.uploads == 1 &&
           trace.draws == 1 && trace.swaps == 1 && trace.seen == frame);
    assert(frame[0] == 1 && frame[11] == 12);

    trace.upload_ok = 0;
    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 2, 2));
    assert(trace.uploads == 2 && trace.draws == 1 && trace.swaps == 1);
    trace.upload_ok = 1;
    trace.draw_ok = 0;
    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 2, 2));
    assert(trace.uploads == 3 && trace.draws == 2 && trace.swaps == 1);
    trace.draw_ok = 1;
    trace.query_ok = 0;
    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 2, 2));
    assert(trace.uploads == 3 && trace.swaps == 1);
    trace.query_ok = 1;

    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame)-1, 2, 2));
    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 0, 2));
    assert(!vh_switch_present_upstream_frame(NULL, frame, sizeof(frame), 2, 2));
    assert(trace.uploads == 3 && trace.swaps == 1);
    trace.swap_ok = 0;
    assert(!vh_switch_present_upstream_frame(&hook, frame, sizeof(frame), 2, 2));
    assert(trace.uploads == 4 && trace.draws == 3 && trace.swaps == 2);
    puts("Upstream presentation hook tests passed.");
    return 0;
}
