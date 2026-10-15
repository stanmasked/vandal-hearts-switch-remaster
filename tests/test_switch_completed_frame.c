#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/switch_completed_frame.h"

static const uint8_t *seen_pixels;
static size_t seen_stride;
static int seen_width, seen_height, uploads, draws;
static int accept_upload = 1, accept_draw = 1;
static uint8_t seen_top[6];

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *presenter,
                                     const VhRgb24Frame *frame) {
    const uint8_t *top;
    assert(presenter && presenter->initialized);
    top = vh_rgb24_top_row(frame, 0);
    assert(top);
    seen_pixels = frame->pixels;
    seen_stride = frame->stride_bytes;
    seen_width = frame->width;
    seen_height = frame->height;
    memcpy(seen_top, top, sizeof(seen_top));
    ++uploads;
    return accept_upload;
}
int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *presenter, int w, int h) {
    assert(presenter && w == 1280 && h == 720);
    ++draws;
    return accept_draw;
}
int main(void) {
    VhSwitchRgb24Presenter presenter = {0};
    uint8_t completed[] = {
        1,2,3, 4,5,6, /* lower row */
        10,11,12, 13,14,15 /* upper row, e.g. OSD applied */
    };
    presenter.initialized = 1;
    assert(vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 1 && draws == 1);
    assert(seen_pixels == completed && seen_stride == 6);
    assert(seen_width == 2 && seen_height == 2);
    assert(memcmp(seen_top, completed + 6, 6) == 0);
    /* No copy or mutation of the composited source frame. */
    assert(completed[6] == 10 && completed[11] == 15);

    /* A later composited frame reuses the borrowed storage without stale pixels. */
    completed[6] = 77;
    assert(vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 2 && draws == 2);
    assert(seen_pixels == completed && seen_top[0] == 77);

    /* Upload failure aborts presentation before any draw. */
    accept_upload = 0;
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 3 && draws == 2);
    accept_upload = 1;

    /* Draw failure is propagated, and a later frame may recover. */
    accept_draw = 0;
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 4 && draws == 3);
    accept_draw = 1;
    assert(vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 5 && draws == 4);
    assert(seen_pixels == completed && seen_top[0] == 77);

    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed) - 1, 2, 2, 1280, 720));
    assert(!vh_switch_present_completed_rgb24(&presenter, NULL,
        sizeof(completed), 2, 2, 1280, 720));
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 0, 2, 1280, 720));
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 0, 720));
    /* Extremely large dimensions cannot bypass the known allocation bound. */
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), INT32_MAX, INT32_MAX, 1280, 720));
    presenter.initialized = 0;
    assert(!vh_switch_present_completed_rgb24(&presenter, completed,
        sizeof(completed), 2, 2, 1280, 720));
    assert(uploads == 5 && draws == 4);
    puts("Completed RGB24 frame handoff tests passed.");
    return 0;
}
