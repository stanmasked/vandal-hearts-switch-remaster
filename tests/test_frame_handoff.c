#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include "../source/frame_handoff.h"

typedef struct {
    int calls;
    const uint8_t *top_row;
    const uint8_t *bottom_row;
    uint8_t top_left_red;
    int result;
} Capture;

static int consume(void *opaque, const VhRgb24Frame *frame) {
    Capture *capture = (Capture *)opaque;
    ++capture->calls;
    capture->top_row = vh_rgb24_top_row(frame, 0);
    capture->bottom_row = vh_rgb24_top_row(frame, frame->height - 1);
    capture->top_left_red = capture->top_row[0];
    return capture->result;
}

int main(void) {
    uint8_t pixels[18] = {
        1, 2, 3, 4, 5, 6, 7, 8, 9,
        10, 11, 12, 13, 14, 15, 16, 17, 18
    };
    VhRgb24Frame frame = {pixels, 9u, 3, 2};
    Capture capture = {0};

    /* A nonzero callback result is normalized to success. */
    capture.result = 42;
    assert(vh_frame_handoff(&frame, consume, &capture) == 1);
    assert(capture.calls == 1);
    assert(capture.top_row == pixels + 9);
    assert(capture.bottom_row == pixels);
    assert(capture.top_left_red == 10);

    /* The callback observes current borrowed bytes, not a stale copy. */
    pixels[9] = 99;
    assert(vh_frame_handoff(&frame, consume, &capture) == 1);
    assert(capture.calls == 2 && capture.top_left_red == 99);

    capture.result = 0;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    assert(capture.calls == 3);

    /* Invalid metadata must never call the consumer. */
    frame.stride_bytes = 12u;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    frame.stride_bytes = 9u;
    frame.pixels = NULL;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    frame.pixels = pixels;
    frame.width = 0;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    frame.width = 3;
    frame.height = -1;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    frame.height = 2;
    assert(vh_frame_handoff(NULL, consume, &capture) == 0);
    assert(vh_frame_handoff(&frame, NULL, &capture) == 0);
    assert(capture.calls == 3);

    puts("Frame handoff tests passed.");
    return 0;
}
