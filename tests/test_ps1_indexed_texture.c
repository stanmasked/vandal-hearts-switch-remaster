#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/ps1_indexed_texture.h"
#include "../source/ft4_textured_quad.h"

#define ATLAS_W 256u
#define ATLAS_H 256u
#define ATLAS_STRIDE 128u
#define CROPPED 16u
#define FB_W 20
#define FB_H 20
#define FB_STRIDE 24
#define CLEAR 0x76543210u

static uint8_t atlas[ATLAS_STRIDE * ATLAS_H];
static uint8_t clut_le[32];
static uint32_t crop[18 * 16];
static uint32_t fb[FB_STRIDE * FB_H];
static VhPs1Clut4Stats stats;

static uint32_t pack_rgba(uint8_t r, uint8_t g, uint8_t b, void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) | ((uint32_t)b << 16) |
           ((uint32_t)g << 8) | (uint32_t)r;
}
static void set_color(unsigned index, uint16_t word) {
    clut_le[index * 2u] = (uint8_t)word;
    clut_le[index * 2u + 1] = (uint8_t)(word >> 8);
}
static uint16_t raw_color(unsigned index) {
    return (uint16_t)((index & 31u) |
                      (((index * 3u) & 31u) << 5) |
                      (((index * 5u) & 31u) << 10) |
                      (index == 3u ? 0x8000u : 0u));
}
static uint32_t expected_color(unsigned index) {
    uint8_t r, g, b;
    vh_ps1_bgr555_rgb888(raw_color(index), &r, &g, &b);
    return pack_rgba(r, g, b, NULL);
}
static void init(void) {
    unsigned u, v;
    memset(atlas, 0, sizeof(atlas));
    for (u = 0; u < 16; ++u) set_color(u, raw_color(u));
    set_color(0, 0);
    for (v = 0; v < 16; ++v) {
        for (u = 0; u < 16; ++u) {
            unsigned index = (u + 3 * v) & 15u;
            unsigned byte = (unsigned)((192 + v) * ATLAS_STRIDE + (240 + u) / 2);
            if (((240 + u) & 1u) == 0) {
                atlas[byte] = (uint8_t)((atlas[byte] & 0xf0u) | index);
            } else {
                atlas[byte] = (uint8_t)((atlas[byte] & 0x0fu) | (index << 4));
            }
        }
    }
}
static void test_nibble_and_palette_raw(void) {
    uint8_t index = 99;
    uint16_t word = 123;
    uint8_t r, g, b;
    init();
    assert(vh_ps1_4bpp_read_index(atlas, sizeof(atlas),
                                  ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                  240, 192, &index) && index == 0);
    assert(vh_ps1_4bpp_read_index(atlas, sizeof(atlas),
                                  ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                  241, 192, &index) && index == 1);
    assert(vh_ps1_4bpp_read_index(atlas, sizeof(atlas),
                                  ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                  240, 193, &index) && index == 3);
    assert(vh_ps1_clut4_read_raw(clut_le, sizeof(clut_le), 3, &word));
    assert(word == raw_color(3) && !!(word & 0x8000u));
    vh_ps1_bgr555_rgb888(0x001fu, &r, &g, &b);
    assert(r == 255 && g == 0 && b == 0);
    vh_ps1_bgr555_rgb888(0x03e0u, &r, &g, &b);
    assert(r == 0 && g == 255 && b == 0);
    vh_ps1_bgr555_rgb888(0x7c00u, &r, &g, &b);
    assert(r == 0 && g == 0 && b == 255);
    vh_ps1_bgr555_rgb888(0x8000u, &r, &g, &b);
    assert(r == 0 && g == 0 && b == 0); /* STP is metadata, not alpha. */
}
static void test_decode_then_draw_ft4_with_exact_pixel_orientation(void) {
    VhCanvas canvas = {fb, FB_STRIDE, FB_W, FB_H};
    VhFt4Point face[4] = {{1, 1}, {17, 1}, {17, 17}, {1, 17}};
    VhFt4Vertex gpu[4];
    size_t count, row, col, zeros = 0, stps = 0;
    for (row = 0; row < FB_STRIDE * FB_H; ++row) fb[row] = CLEAR;
    for (row = 0; row < 18 * 16; ++row) crop[row] = CLEAR;
    assert(vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        crop, 18, pack_rgba, NULL, &stats));
    assert(stats.pixels_decoded == 256);
    for (row = 0; row < 16; ++row) {
        for (col = 0; col < 16; ++col) {
            unsigned index = (unsigned)((col + 3 * row) & 15u);
            uint32_t color = index == 0 ? UINT32_C(0xff000000) : expected_color(index);
            assert(crop[row * 18 + col] == color);
            zeros += index == 0;
            stps += index == 3;
        }
        assert(crop[row * 18 + 16] == CLEAR);
        assert(crop[row * 18 + 17] == CLEAR);
    }
    assert(stats.transparent_zero_pixels == zeros);
    assert(stats.stp_flag_pixels == stps);
    assert(vh_ft4_from_face_perimeter(face, 0, 0, 15, 15, gpu));
    count = vh_canvas_draw_ft4_rgba32(&canvas, crop, 16, 16, 18, gpu);
    assert(count >= 256);
    for (row = 0; row < FB_H; ++row) {
        for (col = 0; col < FB_STRIDE; ++col) {
            uint32_t want = CLEAR;
            if (col >= 1 && col <= 16 && row >= 1 && row <= 16)
                want = crop[(row - 1) * 18 + (col - 1)];
            assert(fb[row * FB_STRIDE + col] == want);
        }
    }
}
static void test_invalid_parameters_cannot_write(void) {
    uint8_t index = 99;
    uint16_t word = 123;
    VhPs1Clut4Stats old = {13, 21, 34};
    size_t i;
    for (i = 0; i < 18 * 16; ++i) crop[i] = CLEAR;
    stats = old;
    assert(!vh_ps1_4bpp_read_index(atlas, sizeof(atlas) - 1,
                                    ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                    240, 192, &index));
    assert(!vh_ps1_4bpp_read_index(atlas, sizeof(atlas),
                                    ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                    256, 192, &index));
    assert(!vh_ps1_4bpp_read_index(atlas, sizeof(atlas),
                                    ATLAS_W, ATLAS_H, ATLAS_STRIDE,
                                    240, 256, &index));
    assert(index == 99);
    assert(!vh_ps1_clut4_read_raw(clut_le, 31, 3, &word));
    assert(!vh_ps1_clut4_read_raw(clut_le, sizeof(clut_le), 16, &word));
    assert(word == 123);
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, 31, 240, 192, 16, 16,
        crop, 18, pack_rgba, NULL, &stats));
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 252, 192, 16, 16,
        crop, 18, pack_rgba, NULL, &stats));
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        crop, 15, pack_rgba, NULL, &stats));
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        crop, 18, NULL, NULL, &stats));
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), SIZE_MAX, ATLAS_H, SIZE_MAX,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        crop, 18, pack_rgba, NULL, &stats));
    assert(!vh_ps1_decode_clut4_crop(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        crop, SIZE_MAX, pack_rgba, NULL, &stats));
    assert(stats.transparent_zero_pixels == old.transparent_zero_pixels);
    assert(stats.stp_flag_pixels == old.stp_flag_pixels);
    assert(stats.pixels_decoded == old.pixels_decoded);
    for (i = 0; i < 18 * 16; ++i) assert(crop[i] == CLEAR);
}
static uint32_t test_stp_blend(uint32_t dst, uint32_t src, void *context) {
    size_t *calls = (size_t *)context;
    assert(dst == CLEAR);
    assert(src != CLEAR);
    ++(*calls);
    return UINT32_C(0xfaceb00c); /* Visible sentinel, not a PS1 ABR formula. */
}

static void test_classified_clut_mask_ft4_and_optional_blend(void) {
    uint8_t classes[18 * 16];
    uint32_t decoded[18 * 16];
    VhFt4Point face[4] = {{1, 1}, {17, 1}, {17, 17}, {1, 17}};
    VhFt4Vertex gpu[4];
    VhCanvas canvas = {fb, FB_STRIDE, FB_W, FB_H};
    VhPs1Clut4Stats result = {0, 0, 0};
    size_t row, col, stp_calls = 0, count = 0, visible = 0, flags_stp = 0;
    assert(vh_ps1_classify_clut_word(0) == VH_PS1_TEXEL_TRANSPARENT);
    assert(vh_ps1_classify_clut_word(0x7fffu) == VH_PS1_TEXEL_OPAQUE);
    assert(vh_ps1_classify_clut_word(0x8000u) == VH_PS1_TEXEL_STP);
    assert(vh_ps1_classify_clut_word(0xffffu) == VH_PS1_TEXEL_STP);
    memset(classes, 0xa5, sizeof(classes));
    for (row = 0; row < 18 * 16; ++row) decoded[row] = CLEAR;
    assert(vh_ps1_decode_clut4_crop_classified(
        atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
        clut_le, sizeof(clut_le), 240, 192, 16, 16,
        decoded, 18, classes, 18, pack_rgba, NULL, &result));
    for (row = 0; row < 16; ++row) {
        for (col = 0; col < 16; ++col) {
            unsigned i = (unsigned)((col + 3 * row) & 15u);
            uint8_t expected = i == 0 ? VH_PS1_TEXEL_TRANSPARENT :
                (i == 3 ? VH_PS1_TEXEL_STP : VH_PS1_TEXEL_OPAQUE);
            assert(classes[row * 18 + col] == expected);
            visible += expected != VH_PS1_TEXEL_TRANSPARENT;
            flags_stp += expected == VH_PS1_TEXEL_STP;
        }
        assert(classes[row * 18 + 16] == 0xa5);
        assert(classes[row * 18 + 17] == 0xa5);
    }
    assert(result.transparent_zero_pixels == 16);
    assert(result.stp_flag_pixels == flags_stp);
    assert(result.pixels_decoded == 256);
    assert(vh_ft4_from_face_perimeter(face, 0, 0, 15, 15, gpu));

    for (row = 0; row < FB_STRIDE * FB_H; ++row) fb[row] = CLEAR;
    count = vh_canvas_draw_ft4_classified_rgba32(
        &canvas, decoded, 16, 16, 18, gpu,
        classes, 18, test_stp_blend, &stp_calls);
    assert(count >= visible);
    assert(stp_calls >= flags_stp);
    for (row = 0; row < 16; ++row) {
        for (col = 0; col < 16; ++col) {
            uint8_t klass = classes[row * 18 + col];
            uint32_t expected = klass == VH_PS1_TEXEL_TRANSPARENT ? CLEAR :
                (klass == VH_PS1_TEXEL_STP ? UINT32_C(0xfaceb00c) :
                 decoded[row * 18 + col]);
            assert(fb[(row + 1) * FB_STRIDE + col + 1] == expected);
        }
        assert(fb[(row + 1) * FB_STRIDE] == CLEAR);
        assert(fb[(row + 1) * FB_STRIDE + 17] == CLEAR);
    }

    /* No blend callback => STP is copied, but zero still punches through. */
    for (row = 0; row < FB_STRIDE * FB_H; ++row) fb[row] = CLEAR;
    assert(vh_canvas_draw_ft4_classified_rgba32(
        &canvas, decoded, 16, 16, 18, gpu, classes, 18, NULL, NULL) >= visible);
    for (row = 0; row < 16; ++row)
        for (col = 0; col < 16; ++col) {
            uint8_t klass = classes[row * 18 + col];
            assert(fb[(row + 1) * FB_STRIDE + col + 1] ==
                   (klass ? decoded[row * 18 + col] : CLEAR));
        }

    /* Invalid buffer strides must not modify the framebuffer or statistics. */
    assert(vh_canvas_draw_ft4_classified_rgba32(
        &canvas, decoded, 16, 16, 18, gpu, classes, 15, NULL, NULL) == 0);
    assert(vh_canvas_draw_ft4_classified_rgba32(
        &canvas, decoded, 16, 16, 18, gpu, classes, SIZE_MAX, NULL, NULL) == 0);
    {
        VhPs1Clut4Stats untouched = {9, 8, 7};
        uint8_t invalid_classes[18 * 16];
        memset(invalid_classes, 0x55, sizeof(invalid_classes));
        assert(!vh_ps1_decode_clut4_crop_classified(
            atlas, sizeof(atlas), ATLAS_W, ATLAS_H, ATLAS_STRIDE,
            clut_le, sizeof(clut_le), 240, 192, 16, 16,
            decoded, 18, invalid_classes, 15, pack_rgba, NULL, &untouched));
        assert(untouched.transparent_zero_pixels == 9);
        assert(untouched.stp_flag_pixels == 8);
        assert(untouched.pixels_decoded == 7);
        for (row = 0; row < 18 * 16; ++row)
            assert(invalid_classes[row] == 0x55);
    }
}

int main(void) {
    test_nibble_and_palette_raw();
    test_decode_then_draw_ft4_with_exact_pixel_orientation();
    test_invalid_parameters_cannot_write();
    test_classified_clut_mask_ft4_and_optional_blend();
    puts("PS1 indexed4 CLUT-to-FT4 tests passed");
    return 0;
}
