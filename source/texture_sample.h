#ifndef VH_TEXTURE_SAMPLE_H
#define VH_TEXTURE_SAMPLE_H

#include <stddef.h>
#include <stdint.h>

/*
 * Bounds-checked nearest-neighbor texel lookup for CPU-side diagnostics.
 * u and v are normalized coordinates in [0, 1). No wrapping or clamping is
 * implicit: callers must choose coordinates and sampler policy deliberately.
 * Returns 0 on invalid input/out-of-range coordinates; otherwise writes the
 * packed texel unchanged and returns 1.
 */
static inline int vh_texture_sample_nearest_rgba32(
    const uint32_t *pixels, size_t width, size_t height, size_t stride_pixels,
    float u, float v, uint32_t *out_pixel) {
    size_t x, y;
    if (!pixels || !out_pixel || width == 0 || height == 0 ||
        stride_pixels < width || !(u >= 0.0f && u < 1.0f) ||
        !(v >= 0.0f && v < 1.0f)) {
        return 0;
    }
    x = (size_t)(u * (float)width);
    y = (size_t)(v * (float)height);
    if (x >= width || y >= height) return 0;
    *out_pixel = pixels[y * stride_pixels + x];
    return 1;
}

/* Validate an integer crop rectangle without overflow-prone x + width math. */
static inline int vh_texture_rect_valid(
    size_t texture_width, size_t texture_height,
    size_t x, size_t y, size_t width, size_t height) {
    if (texture_width == 0 || texture_height == 0 ||
        width == 0 || height == 0 || x >= texture_width || y >= texture_height) {
        return 0;
    }
    return width <= texture_width - x && height <= texture_height - y;
}

#endif
