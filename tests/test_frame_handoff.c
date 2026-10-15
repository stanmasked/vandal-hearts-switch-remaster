#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "../source/frame_handoff.h"

typedef struct {
    int calls;
    const uint8_t *top_row;
    int reject;
} Capture;

static int consume(void *opaque, const VhRgb24Frame *frame) {
    Capture *capture = (Capture *)opaque;
    ++capture->calls;
    capture->top_row = vh_rgb24_top_row(frame, 0);
    return !capture->reject;
}

int main(void) {
    uint8_t pixels[18] = {
        1, 2, 3, 4, 5, 6, 7, 8, 9,
        10, 11, 12, 13, 14, 15, 16, 17, 18
    };
    VhRgb24Frame frame = {pixels, 9u, 3, 2};
    Capture capture = {0};

    assert(vh_frame_handoff(&frame, consume, &capture) == 1);
    assert(capture.calls == 1 && capture.top_row == pixels + 9);
    capture.reject = 1;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    assert(capture.calls == 2);

    frame.stride_bytes = 12u;
    assert(vh_frame_handoff(&frame, consume, &capture) == 0);
    assert(capture.calls == 2);
    assert(vh_frame_handoff(NULL, consume, &capture) == 0);
    assert(vh_frame_handoff(&frame, NULL, &capture) == 0);
    assert(capture.calls == 2);

    puts("Frame handoff tests passed.");
    return 0;
}
