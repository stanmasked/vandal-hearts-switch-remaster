#ifndef VANDAL_HEARTS_RGB24_FRAME_H
#define VANDAL_HEARTS_RGB24_FRAME_H

#include <stddef.h>
#include <stdint.h>
#include <limits.h>

/*
 * View of the upstream PC port's presentation buffer:
 * packed RGB24, tightly packed rows, stored bottom-up.
 * The memory is borrowed; the caller must keep it alive while reading.
 */
typedef struct {
    const uint8_t *pixels;
    size_t stride_bytes;
    int width;
    int height;
} VhRgb24Frame;

/* Validate the exact tightly-packed RGB24 contract without overflowing size math. */
static inline int vh_rgb24_frame_valid(const VhRgb24Frame *frame) {
    if (!frame || !frame->pixels || frame->width <= 0 || frame->height <= 0)
        return 0;
    if ((size_t)frame->width > SIZE_MAX / 3u)
        return 0;
    const size_t row_bytes = (size_t)frame->width * 3u;
    if (frame->stride_bytes != row_bytes)
        return 0;
    if ((size_t)frame->height > SIZE_MAX / row_bytes)
        return 0;
    return 1;
}

/*
 * Return a row in conventional top-down image coordinates from the upstream
 * bottom-up buffer. Returns NULL for invalid frames or out-of-range y.
 */
static inline const uint8_t *vh_rgb24_top_row(const VhRgb24Frame *frame, int y) {
    if (!vh_rgb24_frame_valid(frame) || y < 0 || y >= frame->height)
        return NULL;
    return frame->pixels + (size_t)(frame->height - 1 - y) * frame->stride_bytes;
}

#endif
