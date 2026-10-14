#ifndef VANDAL_HEARTS_SOFTWARE_RENDERER_H
#define VANDAL_HEARTS_SOFTWARE_RENDERER_H

#include <stddef.h>
#include <stdint.h>
#include <limits.h>

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

/* Write one pixel if it lies inside the visible canvas. */
static inline void vh_canvas_put_pixel(VhCanvas *canvas, int x, int y,
                                      uint32_t color) {
    if (!canvas || !canvas->pixels || canvas->width <= 0 ||
        canvas->height <= 0 || canvas->stride_pixels < (size_t)canvas->width ||
        x < 0 || y < 0 || x >= canvas->width || y >= canvas->height) {
        return;
    }
    canvas->pixels[(size_t)y * canvas->stride_pixels + (size_t)x] = color;
}

/* Draw clipped horizontal and vertical lines; endpoints are inclusive. */
static inline void vh_canvas_draw_hline(VhCanvas *canvas, int x, int y,
                                        int length, uint32_t color) {
    vh_canvas_fill_rect(canvas, x, y, length, 1, color);
}

static inline void vh_canvas_draw_vline(VhCanvas *canvas, int x, int y,
                                        int length, uint32_t color) {
    vh_canvas_fill_rect(canvas, x, y, 1, length, color);
}


/* Draw a one-pixel rectangle border; width/height are pixel extents. */
static inline void vh_canvas_draw_rect_outline(VhCanvas *canvas, int x, int y,
                                               int width, int height,
                                               uint32_t color) {
    if (width <= 0 || height <= 0) return;

    vh_canvas_draw_hline(canvas, x, y, width, color);

    int64_t bottom = (int64_t)y + height - 1;
    int64_t right = (int64_t)x + width - 1;
    if (height > 1 && bottom >= INT_MIN && bottom <= INT_MAX) {
        vh_canvas_draw_hline(canvas, x, (int)bottom, width, color);
    }
    if (height > 2) {
        vh_canvas_draw_vline(canvas, x, y + 1, height - 2, color);
        if (width > 1 && right >= INT_MIN && right <= INT_MAX) {
            vh_canvas_draw_vline(canvas, (int)right, y + 1,
                                 height - 2, color);
        }
    }
}

#endif
