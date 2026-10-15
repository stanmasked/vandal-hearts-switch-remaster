#include "switch_converted_frame.h"

int vh_switch_present_bgr555(VhSwitchRgb24Presenter *presenter,
                             const uint16_t *vram, size_t vram_pixels,
                             int vram_width, int vram_height,
                             int x, int y, int width, int height,
                             uint8_t *scratch, size_t scratch_bytes,
                             int viewport_width, int viewport_height) {
    size_t required;
    VhRgb24Frame frame;
    if (!presenter || !presenter->initialized ||
        viewport_width <= 0 || viewport_height <= 0 ||
        !vh_rgb24_required(width, height, &required) ||
        scratch_bytes < required)
        return 0;
    if (!vh_frame_from_bgr555(vram, vram_pixels, vram_width, vram_height,
                              x, y, width, height, scratch, scratch_bytes))
        return 0;
    frame.pixels = scratch;
    frame.stride_bytes = (size_t)width * 3u;
    frame.width = width;
    frame.height = height;
    return vh_switch_present_frame(presenter, &frame,
                                    viewport_width, viewport_height);
}

int vh_switch_present_movie_rgb24(VhSwitchRgb24Presenter *presenter,
                                  const uint8_t *movie, size_t movie_bytes,
                                  int width, int height,
                                  uint8_t *scratch, size_t scratch_bytes,
                                  int viewport_width, int viewport_height) {
    size_t required;
    VhRgb24Frame frame;
    if (!presenter || !presenter->initialized ||
        viewport_width <= 0 || viewport_height <= 0 ||
        !vh_rgb24_required(width, height, &required) ||
        scratch_bytes < required)
        return 0;
    if (!vh_frame_from_rgb24_top_down(movie, movie_bytes, width, height,
                                      scratch, scratch_bytes))
        return 0;
    frame.pixels = scratch;
    frame.stride_bytes = (size_t)width * 3u;
    frame.width = width;
    frame.height = height;
    return vh_switch_present_frame(presenter, &frame,
                                    viewport_width, viewport_height);
}
