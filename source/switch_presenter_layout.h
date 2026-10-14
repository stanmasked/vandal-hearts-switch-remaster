#ifndef VANDAL_HEARTS_SWITCH_PRESENTER_LAYOUT_H
#define VANDAL_HEARTS_SWITCH_PRESENTER_LAYOUT_H

#include <stdint.h>

/* Integer destination rectangle for aspect-preserving, centered presentation. */
typedef struct {
    int x;
    int y;
    int width;
    int height;
} VhPresenterRect;

/*
 * Fit a source frame inside a destination viewport without cropping or
 * stretching. Returns 0 for invalid dimensions or a null output pointer.
 * The caller chooses filtering; this helper only computes geometry.
 */
static inline int vh_presenter_fit_rect(
    int source_width, int source_height,
    int viewport_width, int viewport_height,
    VhPresenterRect *out)
{
    if (!out || source_width <= 0 || source_height <= 0 ||
        viewport_width <= 0 || viewport_height <= 0)
        return 0;

    int width;
    int height;
    const uint64_t width_limited_height =
        (uint64_t)(unsigned)viewport_width * (uint64_t)(unsigned)source_height /
        (uint64_t)(unsigned)source_width;

    if (width_limited_height <= (uint64_t)(unsigned)viewport_height) {
        width = viewport_width;
        height = (int)width_limited_height;
    } else {
        const uint64_t height_limited_width =
            (uint64_t)(unsigned)viewport_height * (uint64_t)(unsigned)source_width /
            (uint64_t)(unsigned)source_height;
        width = (int)height_limited_width;
        height = viewport_height;
    }

    if (width <= 0 || height <= 0)
        return 0;

    out->width = width;
    out->height = height;
    out->x = (viewport_width - width) / 2;
    out->y = (viewport_height - height) / 2;
    return 1;
}

#endif
