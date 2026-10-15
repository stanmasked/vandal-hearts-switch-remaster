#include "switch_managed_frame.h"

/* Reject sources inside the owned allocation before reserve can realloc it. */
static int scratch_overlaps_source(const VhRgb24Scratch *scratch,
                                  const void *source, size_t source_bytes) {
    uintptr_t a, b;
    if (!scratch->pixels || !scratch->capacity || !source_bytes)
        return 0;
    a = (uintptr_t)scratch->pixels;
    b = (uintptr_t)source;
    return a <= b ? b - a < scratch->capacity : a - b < source_bytes;
}

int vh_switch_present_managed_bgr555(VhSwitchRgb24Presenter *presenter,
    VhRgb24Scratch *scratch, size_t max_bytes,
    const uint16_t *vram, size_t vram_pixels, int vram_width, int vram_height,
    int x, int y, int width, int height, int viewport_width, int viewport_height) {
    size_t needed;
    if (!presenter || !presenter->initialized || !scratch || !vram ||
        viewport_width <= 0 || viewport_height <= 0 ||
        !vh_rgb24_required(width, height, &needed) || needed > max_bytes ||
        vram_width <= 0 || vram_height <= 0 ||
        (size_t)vram_width > SIZE_MAX / (size_t)vram_height ||
        vram_pixels < (size_t)vram_width * (size_t)vram_height ||
        x < 0 || y < 0 || x > vram_width || y > vram_height ||
        width > vram_width - x || height > vram_height - y ||
        (size_t)vram_width * (size_t)vram_height > SIZE_MAX / sizeof(*vram) ||
        scratch_overlaps_source(scratch, vram,
            (size_t)vram_width * (size_t)vram_height * sizeof(*vram)))
        return 0;
    if (!vh_rgb24_scratch_reserve(scratch, width, height, max_bytes))
        return 0;
    return vh_switch_present_bgr555(presenter, vram, vram_pixels,
        vram_width, vram_height, x, y, width, height,
        scratch->pixels, scratch->capacity, viewport_width, viewport_height);
}

int vh_switch_present_managed_movie(VhSwitchRgb24Presenter *presenter,
    VhRgb24Scratch *scratch, size_t max_bytes,
    const uint8_t *movie, size_t movie_bytes, int width, int height,
    int viewport_width, int viewport_height) {
    size_t needed;
    if (!presenter || !presenter->initialized || !scratch || !movie ||
        viewport_width <= 0 || viewport_height <= 0 ||
        !vh_rgb24_required(width, height, &needed) || needed > max_bytes ||
        movie_bytes < needed ||
        scratch_overlaps_source(scratch, movie, needed))
        return 0;
    if (!vh_rgb24_scratch_reserve(scratch, width, height, max_bytes))
        return 0;
    return vh_switch_present_movie_rgb24(presenter, movie, movie_bytes,
        width, height, scratch->pixels, scratch->capacity,
        viewport_width, viewport_height);
}
