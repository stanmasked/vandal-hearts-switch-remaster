#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../source/switch_frame_bridge.h"

static int uploads;
static int draws;
static int upload_ok = 1;
static int draw_ok = 1;
static const uint8_t *observed_top;

int vh_switch_rgb24_presenter_upload(VhSwitchRgb24Presenter *p,
                                      const VhRgb24Frame *frame) {
    assert(p && p->initialized);
    ++uploads;
    observed_top = vh_rgb24_top_row(frame, 0);
    return upload_ok;
}

int vh_switch_rgb24_presenter_draw(VhSwitchRgb24Presenter *p,
                                    int width, int height) {
    assert(p && width > 0 && height > 0);
    ++draws;
    return draw_ok;
}

int main(void) {
    uint8_t pixels[18] = {0};
    VhRgb24Frame frame = {pixels, 9u, 3, 2};
    VhSwitchRgb24Presenter presenter;
    memset(&presenter, 0, sizeof(presenter));
    presenter.initialized = 1;

    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 1);
    assert(uploads == 1 && draws == 1 && observed_top == pixels + 9);

    upload_ok = 0;
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 0);
    assert(uploads == 2 && draws == 1);
    upload_ok = 1;

    draw_ok = 0;
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 0);
    assert(uploads == 3 && draws == 2);
    draw_ok = 1;

    frame.stride_bytes = 12u;
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 0);
    assert(uploads == 3 && draws == 2);
    frame.stride_bytes = 9u;

    /* A rejected frame must not poison the next valid presentation. */
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 1);
    assert(uploads == 4 && draws == 3);

    assert(vh_switch_present_frame(NULL, &frame, 1280, 720) == 0);
    assert(vh_switch_present_frame(&presenter, NULL, 1280, 720) == 0);
    assert(vh_switch_present_frame(&presenter, &frame, 0, 720) == 0);
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 0) == 0);
    assert(vh_switch_present_frame(&presenter, &frame, -1, 720) == 0);
    assert(vh_switch_present_frame(&presenter, &frame, 1280, -1) == 0);
    assert(uploads == 4 && draws == 3);

    presenter.initialized = 0;
    assert(vh_switch_present_frame(&presenter, &frame, 1280, 720) == 0);
    assert(uploads == 4 && draws == 3);
    puts("Switch frame bridge tests passed.");
    return 0;
}
