#include "switch_completed_frame.h"
#include "frame_conversion.h"

int vh_switch_present_completed_rgb24(VhSwitchRgb24Presenter *presenter,
                                      const uint8_t *pixels,
                                      size_t pixel_bytes,
                                      int width, int height,
                                      int viewport_width, int viewport_height) {
    size_t required;
    VhRgb24Frame frame;
    if (!pixels || !vh_rgb24_required(width, height, &required) ||
        pixel_bytes < required)
        return 0;
    frame.pixels = pixels;
    frame.width = width;
    frame.height = height;
    frame.stride_bytes = (size_t)width * 3u;
    return vh_switch_present_frame(presenter, &frame, viewport_width, viewport_height);
}
