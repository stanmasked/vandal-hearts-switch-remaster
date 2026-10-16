#ifndef VH_MAP02_TERRAIN_LIGHTING_H
#define VH_MAP02_TERRAIN_LIGHTING_H

/*
 * Portable MAP02 terrain lighting reference.
 *
 * Pinned US PC-port src/core/graphics.c uses for normal/edge tiles:
 *   shade = clamp(max(5,otz) - 150, 0, 256);
 *   poly.r/g/b = sideLight[channel] - ((sideLight[channel] * shade) >> 8);
 *
 * This models the terrain's per-face GPU modulation color. Actual
 * side-light tables depend on live GTE lighting and are caller-owned.
 * Overhead terrain instead sets RGB to caller-specified brightness.
 *
 * PS1 textured polygon RGB modulation is approximated in 8-bit RGB
 * (texel * command color / 128), with saturation at 255. This does
 * not emulate PS1 dither, GPU quantization, mask bits, texture windows,
 * final 15-bit framebuffer rounding, or GTE projective transforms.
 */
#include <stddef.h>
#include <stdint.h>
#include "ps1_abr_blend.h"

#define VH_MAP02_SIDE_LIGHT_COUNT 26u

typedef struct {
    uint8_t red;
    uint8_t green;
    uint8_t blue;
} VhMap02LightRgb;

static inline int vh_map02_depth_fade(int otz) {
    int fade;
    if (otz < 5) otz = 5;
    fade = otz - 150;
    if (fade < 0) return 0;
    if (fade > 256) return 256;
    return fade;
}

static inline uint8_t vh_map02_distance_shade_channel(uint8_t side, int otz) {
    int fade = vh_map02_depth_fade(otz);
    return (uint8_t)((int)side - (((int)side * fade) >> 8));
}

static inline VhMap02LightRgb vh_map02_face_light(
    VhMap02LightRgb side, int otz) {
    VhMap02LightRgb result;
    result.red = vh_map02_distance_shade_channel(side.red, otz);
    result.green = vh_map02_distance_shade_channel(side.green, otz);
    result.blue = vh_map02_distance_shade_channel(side.blue, otz);
    return result;
}

/* Exact source rule for overhead renderer: setRGB0(brightness, ...).
 * Brightness is clipped to the 8-bit GPU command component range.
 */
static inline VhMap02LightRgb vh_map02_overhead_light(int brightness) {
    uint8_t value;
    VhMap02LightRgb result;
    if (brightness < 0) brightness = 0;
    if (brightness > 255) brightness = 255;
    value = (uint8_t)brightness;
    result.red = result.green = result.blue = value;
    return result;
}

static inline int vh_map02_select_side_light(
    const VhMap02LightRgb *table, size_t count,
    unsigned shade_index, int otz,
    VhMap02LightRgb *out) {
    if (!table || !out || count < VH_MAP02_SIDE_LIGHT_COUNT ||
        shade_index >= VH_MAP02_SIDE_LIGHT_COUNT) return 0;
    *out = vh_map02_face_light(table[shade_index], otz);
    return 1;
}

/* Reference multiplication for a textured, non-raw PS1 GP0 0x2c/0x2e
 * polygon. GPU command color 128 is approximately neutral (1.0x).
 * Intermediate 8-bit RGB is explicit; no alpha interpretation.
 */
static inline uint8_t vh_map02_modulate_channel(
    uint8_t texel, uint8_t command_color) {
    unsigned modulated = ((unsigned)texel * command_color) >> 7;
    return (uint8_t)(modulated > 255u ? 255u : modulated);
}

static inline uint32_t vh_map02_tint_pixel(
    uint32_t pixel, VhMap02LightRgb light,
    VhPs1RgbUnpackFn unpack, VhPs1RgbPackFn pack, void *context) {
    uint8_t r, g, b;
    if (!unpack || !pack) return pixel;
    unpack(pixel, &r, &g, &b, context);
    return pack(vh_map02_modulate_channel(r, light.red),
                vh_map02_modulate_channel(g, light.green),
                vh_map02_modulate_channel(b, light.blue), context);
}

/* Supports in-place and independent destination buffers; checked strides.
 * The per-texel zero/STP classification is deliberately unchanged and
 * must still be passed to vh_canvas_draw_ft4_classified_rgba32.
 * On bad input, no pixels are written.
 */
static inline int vh_map02_tint_crop_rgba32(
    const uint32_t *source, size_t source_stride,
    uint32_t *destination, size_t destination_stride,
    size_t width, size_t height, VhMap02LightRgb light,
    VhPs1RgbUnpackFn unpack, VhPs1RgbPackFn pack,
    void *context) {
    size_t x, y;
    if (!source || !destination || !unpack || !pack ||
        width == 0 || height == 0 ||
        source_stride < width || destination_stride < width ||
        source_stride > SIZE_MAX / height ||
        destination_stride > SIZE_MAX / height) return 0;
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            destination[y * destination_stride + x] =
                vh_map02_tint_pixel(source[y * source_stride + x],
                                   light, unpack, pack, context);
        }
    }
    return 1;
}

#endif
