#ifndef VANDAL_HEARTS_SOFTWARE_RENDERER_H
#define VANDAL_HEARTS_SOFTWARE_RENDERER_H

#include <stddef.h>
#include <stdint.h>

/*
 * Platform-neutral view of a packed 32-bit software framebuffer.
 * The caller owns the memory and defines the pixel format via the colors
 * passed to drawing functions.
 */
typedef struct {
    uint32_t *pixels;
    size_t stride_pixels;
    int width;
    int height;
} VhCanvas;

/* Fill a clipped rectangle. Invalid canvases and empty rectangles are no-ops. */
static inline void vh_canvas_fill_rect(VhCanvas *canvas, int x, int y,
                                       int width, int height, uint32_t color) {
    if (!canvas || !canvas->pixels || canvas->width <= 0 ||
        canvas->height <= 0 || canvas->stride_pixels < (size_t)canvas->width ||
        width <= 0 || height <= 0) {
        return;
    }

    /* Use 64-bit bounds so hostile/accidental large coordinates cannot overflow. */
    int64_t left = x;
    int64_t top = y;
    int64_t right = left + (int64_t)width;
    int64_t bottom = top + (int64_t)height;

    if (left < 0) left = 0;
    if (top < 0) top = 0;
    if (right > canvas->width) right = canvas->width;
    if (bottom > canvas->height) bottom = canvas->height;
    if (left >= right || top >= bottom) return;

    for (int64_t row = top; row < bottom; ++row) {
        uint32_t *line = canvas->pixels + (size_t)row * canvas->stride_pixels;
        for (int64_t col = left; col < right; ++col) {
            line[col] = color;
        }
    }
}

#endif
