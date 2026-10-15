#include "switch_frame_bridge.h"

static int upload_frame(void *context, const VhRgb24Frame *frame) {
    return vh_switch_rgb24_presenter_upload(
        (VhSwitchRgb24Presenter *)context, frame);
}

int vh_switch_present_frame(VhSwitchRgb24Presenter *presenter,
                            const VhRgb24Frame *frame,
                            int viewport_width, int viewport_height) {
    if (!presenter || !presenter->initialized ||
        viewport_width <= 0 || viewport_height <= 0)
        return 0;
    if (!vh_frame_handoff(frame, upload_frame, presenter))
        return 0;
    return vh_switch_rgb24_presenter_draw(
        presenter, viewport_width, viewport_height);
}
