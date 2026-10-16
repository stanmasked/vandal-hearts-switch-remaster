#ifndef VH_PS1_INDEXED_TEXTURE_H
#define VH_PS1_INDEXED_TEXTURE_H

/*
 * Portable 4-bpp indexed-texel / 16-color CLUT decoder.
 *
 * This is source pixel decoding, NOT PS1 GPU blending: raw BGR555/STP is
 * preserved for inspection; the caller selects its own destination RGBA32
 * packing. Color zero and STP bit15 are counted, not silently discarded.
 *
 * Atlas coordinates are 4-bpp logical texel coordinates: even u selects
 * the low nibble, odd u the high nibble (matching original MAP02 audit).
 * All buffers are caller-owned and length-checked before any writes.
 */
#include <stddef.h>
#include <stdint.h>
#include <limits.h>

typedef uint32_t (*VhPs1RgbPackFn)(
    uint8_t red, uint8_t green, uint8_t blue, void *context);

typedef struct {
    size_t transparent_zero_pixels;
    size_t stp_flag_pixels;
    size_t pixels_decoded;
} VhPs1Clut4Stats;

static inline uint8_t vh_ps1_5_to_8(unsigned channel) {
    return (uint8_t)((channel << 3) | (channel >> 2));
}

static inline void vh_ps1_bgr555_rgb888(
    uint16_t word, uint8_t *red, uint8_t *green, uint8_t *blue) {
    if (red)   *red   = vh_ps1_5_to_8(word & 31u);
    if (green) *green = vh_ps1_5_to_8((word >> 5) & 31u);
    if (blue)  *blue  = vh_ps1_5_to_8((word >> 10) & 31u);
}

/* Checked read from a packed row-strided 4-bpp atlas. */
static inline int vh_ps1_4bpp_read_index(
    const uint8_t *atlas, size_t atlas_bytes,
    size_t width_texels, size_t height_texels, size_t row_stride_bytes,
    size_t u, size_t v, uint8_t *out_index) {
    size_t offset;
    if (!atlas || !out_index || width_texels == 0 || height_texels == 0 ||
        width_texels > SIZE_MAX - 1 ||
        row_stride_bytes < (width_texels + 1) / 2 ||
        row_stride_bytes > SIZE_MAX / height_texels ||
        atlas_bytes < row_stride_bytes * height_texels ||
        u >= width_texels || v >= height_texels) {
        return 0;
    }
    offset = v * row_stride_bytes + u / 2;
    *out_index = (uint8_t)((atlas[offset] >> ((u & 1u) * 4u)) & 15u);
    return 1;
}

/* Raw little-endian 16-word CLUT read; never assumes host endianness. */
static inline int vh_ps1_clut4_read_raw(
    const uint8_t *clut_le, size_t clut_bytes,
    unsigned index, uint16_t *out_word) {
    size_t offset;
    if (!clut_le || !out_word || clut_bytes < 32 || index >= 16) return 0;
    offset = (size_t)index * 2u;
    *out_word = (uint16_t)((uint16_t)clut_le[offset] |
                           ((uint16_t)clut_le[offset + 1] << 8));
    return 1;
}

/*
 * Decode a rectangular crop to caller-selected packed RGBA32 for FT4.
 * This does not decide transparency or PS1 half-blending: zero and STP
 * information is observable through stats or raw index/palette readers.
 * On invalid inputs, output and stats are left unchanged.
 *
 * With map02 atlas, width=height=256, atlas stride=128, and UVWH
 * (u,v,15,15) corresponds to a crop of exactly 16x16 output pixels.
 */
static inline int vh_ps1_decode_clut4_crop(
    const uint8_t *atlas, size_t atlas_bytes,
    size_t width_texels, size_t height_texels, size_t row_stride_bytes,
    const uint8_t *clut_le, size_t clut_bytes,
    size_t left, size_t top, size_t crop_width, size_t crop_height,
    uint32_t *rgba, size_t output_stride_pixels,
    VhPs1RgbPackFn pack, void *context, VhPs1Clut4Stats *stats) {
    size_t x, y;
    VhPs1Clut4Stats local = {0, 0, 0};
    if (!atlas || !clut_le || !rgba || !pack ||
        width_texels == 0 || height_texels == 0 ||
        width_texels > SIZE_MAX - 1 ||
        row_stride_bytes < (width_texels + 1) / 2 ||
        row_stride_bytes > SIZE_MAX / height_texels ||
        atlas_bytes < row_stride_bytes * height_texels ||
        clut_bytes < 32 ||
        crop_width == 0 || crop_height == 0 ||
        left >= width_texels || top >= height_texels ||
        crop_width > width_texels - left ||
        crop_height > height_texels - top ||
        output_stride_pixels < crop_width ||
        output_stride_pixels > SIZE_MAX / crop_height) {
        return 0;
    }
    for (y = 0; y < crop_height; ++y) {
        const uint8_t *row = atlas + (top + y) * row_stride_bytes;
        for (x = 0; x < crop_width; ++x) {
            const size_t uv = left + x;
            uint8_t index = (uint8_t)((row[uv / 2] >> ((uv & 1u) * 4u)) & 15u);
            const size_t offset = (size_t)index * 2u;
            const uint16_t word = (uint16_t)(
                (uint16_t)clut_le[offset] | ((uint16_t)clut_le[offset + 1] << 8));
            uint8_t red, green, blue;
            vh_ps1_bgr555_rgb888(word, &red, &green, &blue);
            rgba[y * output_stride_pixels + x] = pack(red, green, blue, context);
            local.transparent_zero_pixels += word == 0;
            local.stp_flag_pixels += !!(word & 0x8000u);
            ++local.pixels_decoded;
        }
    }
    if (stats) *stats = local;
    return 1;
}

#endif
