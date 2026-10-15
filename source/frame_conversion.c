#include "frame_conversion.h"
#include <string.h>
#include <stdint.h>

int vh_rgb24_required(int width, int height, size_t *bytes) {
    size_t row;
    if (!bytes || width <= 0 || height <= 0 ||
        (size_t)width > SIZE_MAX / 3u)
        return 0;
    row = (size_t)width * 3u;
    if ((size_t)height > SIZE_MAX / row)
        return 0;
    *bytes = row * (size_t)height;
    return 1;
}

int vh_frame_from_bgr555(const uint16_t *src, size_t src_pixels,
                         int src_width, int src_height,
                         int x, int y, int width, int height,
                         uint8_t *dst, size_t dst_bytes) {
    size_t required;
    int row, col;
    if (!src || !dst || !vh_rgb24_required(width, height, &required) ||
        dst_bytes < required || src_width <= 0 || src_height <= 0 ||
        (size_t)src_width > SIZE_MAX / (size_t)src_height ||
        src_pixels < (size_t)src_width * (size_t)src_height ||
        x < 0 || y < 0 || x > src_width || y > src_height ||
        width > src_width - x || height > src_height - y)
        return 0;
    /* Source and destination must not overlap. */
    for (row = 0; row < height; ++row) {
        const uint16_t *in = src + (size_t)(y + row) * (size_t)src_width + (size_t)x;
        uint8_t *out = dst + (size_t)(height - 1 - row) * (size_t)width * 3u;
        for (col = 0; col < width; ++col) {
            unsigned c = in[col];
            unsigned r = c & 31u, g = (c >> 5u) & 31u, bl = (c >> 10u) & 31u;
            out[(size_t)col * 3u] = (uint8_t)((r << 3u) | (r >> 2u));
            out[(size_t)col * 3u + 1u] = (uint8_t)((g << 3u) | (g >> 2u));
            out[(size_t)col * 3u + 2u] = (uint8_t)((bl << 3u) | (bl >> 2u));
        }
    }
    return 1;
}

int vh_frame_from_rgb24_top_down(const uint8_t *src, size_t src_bytes,
                                 int width, int height,
                                 uint8_t *dst, size_t dst_bytes) {
    size_t required, stride;
    int row;
    if (!src || !dst || !vh_rgb24_required(width, height, &required) ||
        src_bytes < required || dst_bytes < required)
        return 0;
    stride = (size_t)width * 3u;
    /* Requires distinct, non-overlapping source and destination allocations. */
    for (row = 0; row < height; ++row)
        memcpy(dst + (size_t)(height - 1 - row) * stride,
               src + (size_t)row * stride, stride);
    return 1;
}
