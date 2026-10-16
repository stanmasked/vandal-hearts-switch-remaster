#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_terrain_lighting.h"
#include "../source/ft4_textured_quad.h"

#define W 16u
#define H 16u
#define STRIDE 19u
#define FB_W 20
#define FB_H 20
#define FB_STRIDE 24
#define BACK UINT32_C(0xff211809)
#define SENTINEL UINT32_C(0xdecafbad)

static uint32_t source[STRIDE * H];
static uint32_t tinted[STRIDE * H];
static uint8_t masks[W * H];
static uint32_t framebuffer[FB_STRIDE * FB_H];

static uint32_t pack(uint8_t r, uint8_t g, uint8_t b, void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) | ((uint32_t)b << 16) |
           ((uint32_t)g << 8) | (uint32_t)r;
}
static void unpack(uint32_t color, uint8_t *r, uint8_t *g,
                   uint8_t *b, void *ctx) {
    (void)ctx;
    *r = (uint8_t)color;
    *g = (uint8_t)(color >> 8);
    *b = (uint8_t)(color >> 16);
}

static void test_distance_shade_matches_original_integer_formula(void) {
    assert(vh_map02_depth_fade(INT_MIN) == 0);
    assert(vh_map02_depth_fade(5) == 0);
    assert(vh_map02_depth_fade(150) == 0);
    assert(vh_map02_depth_fade(151) == 1);
    assert(vh_map02_depth_fade(278) == 128);
    assert(vh_map02_depth_fade(405) == 255);
    assert(vh_map02_depth_fade(406) == 256);
    assert(vh_map02_depth_fade(INT_MAX) == 256);
    for (unsigned side = 0; side < 256; ++side) {
        for (int otz = 0; otz < 900; ++otz) {
            const int fade = otz < 150 ? 0 :
                (otz - 150 > 256 ? 256 : otz - 150);
            assert(vh_map02_distance_shade_channel((uint8_t)side, otz)
                   == (uint8_t)(side - ((side * (unsigned)fade) >> 8)));
        }
    }
    {
        VhMap02LightRgb red = {255, 12, 0};
        VhMap02LightRgb at_150 = vh_map02_face_light(red, 150);
        VhMap02LightRgb at_278 = vh_map02_face_light(red, 278);
        VhMap02LightRgb at_406 = vh_map02_face_light(red, 406);
        assert(at_150.red == 255 && at_150.green == 12);
        assert(at_278.red == 128 && at_278.green == 6);
        assert(at_406.red == 0 && at_406.green == 0);
    }
}

static void test_side_light_table_and_overhead_are_different(void) {
    VhMap02LightRgb table[26] = {{0, 0, 0}};
    VhMap02LightRgb output = {99, 99, 99};
    VhMap02LightRgb over;
    table[0] = (VhMap02LightRgb){128, 64, 32};
    table[25] = (VhMap02LightRgb){200, 150, 100};
    assert(vh_map02_select_side_light(table, 26, 25, 278, &output));
    assert(output.red == 100 && output.green == 75 && output.blue == 50);
    assert(vh_map02_select_side_light(table, 26, 0, 150, &output));
    assert(output.red == 128 && output.green == 64 && output.blue == 32);
    assert(!vh_map02_select_side_light(table, 25, 0, 150, &output));
    assert(!vh_map02_select_side_light(table, 26, 26, 150, &output));
    assert(!vh_map02_select_side_light(NULL, 26, 0, 150, &output));
    assert(!vh_map02_select_side_light(table, 26, 0, 150, NULL));
    assert(output.red == 128 && output.green == 64 && output.blue == 32);
    over = vh_map02_overhead_light(-100);
    assert(over.red == 0 && over.green == 0 && over.blue == 0);
    over = vh_map02_overhead_light(2048);
    assert(over.red == 255 && over.green == 255 && over.blue == 255);
    over = vh_map02_overhead_light(100);
    assert(over.red == 100 && over.green == 100 && over.blue == 100);
}

static void test_texture_rgb_modulation_and_buffer_integrity(void) {
    VhMap02LightRgb neutral = {128, 128, 128};
    VhMap02LightRgb dim = vh_map02_face_light(neutral, 278);
    uint32_t clear_copy[STRIDE * H];
    assert(dim.red == 64 && dim.green == 64 && dim.blue == 64);
    assert(vh_map02_modulate_channel(255, 128) == 255);
    assert(vh_map02_modulate_channel(128, 128) == 128);
    assert(vh_map02_modulate_channel(255, 255) == 255);
    assert(vh_map02_modulate_channel(255, 64) == 127);
    assert(vh_map02_modulate_channel(255, 0) == 0);
    assert(vh_map02_tint_pixel(SENTINEL, neutral, NULL, pack, NULL) == SENTINEL);
    for (size_t i = 0; i < STRIDE * H; ++i) {
        source[i] = SENTINEL;
        tinted[i] = SENTINEL;
    }
    for (size_t y = 0; y < H; ++y)
        for (size_t x = 0; x < W; ++x)
            source[y * STRIDE + x] =
                pack((uint8_t)(x * 17), (uint8_t)(y * 17),
                     (uint8_t)((x + y) * 8), NULL);
    assert(vh_map02_tint_crop_rgba32(source, STRIDE, tinted, STRIDE,
                                    W, H, dim, unpack, pack, NULL));
    for (size_t y = 0; y < H; ++y) {
        for (size_t x = 0; x < W; ++x) {
            assert(tinted[y * STRIDE + x] ==
                pack((uint8_t)(((x * 17) * 64u) >> 7),
                     (uint8_t)(((y * 17) * 64u) >> 7),
                     (uint8_t)((((x + y) * 8u) * 64u) >> 7), NULL));
        }
        for (size_t x = W; x < STRIDE; ++x)
            assert(tinted[y * STRIDE + x] == SENTINEL);
    }
    memcpy(clear_copy, tinted, sizeof(tinted));
    assert(!vh_map02_tint_crop_rgba32(source, 15, tinted, STRIDE,
                                     W, H, dim, unpack, pack, NULL));
    assert(!vh_map02_tint_crop_rgba32(source, STRIDE, tinted, 15,
                                     W, H, dim, unpack, pack, NULL));
    assert(!vh_map02_tint_crop_rgba32(source, STRIDE, tinted, STRIDE,
                                     0, H, dim, unpack, pack, NULL));
    assert(!vh_map02_tint_crop_rgba32(source, SIZE_MAX, tinted, STRIDE,
                                     W, H, dim, unpack, pack, NULL));
    assert(!vh_map02_tint_crop_rgba32(source, STRIDE, tinted, STRIDE,
                                     W, H, dim, NULL, pack, NULL));
    assert(!vh_map02_tint_crop_rgba32(NULL, STRIDE, tinted, STRIDE,
                                     W, H, dim, unpack, pack, NULL));
    assert(memcmp(tinted, clear_copy, sizeof(tinted)) == 0);
    assert(vh_map02_tint_crop_rgba32(tinted, STRIDE, tinted, STRIDE,
                                    W, H, neutral, unpack, pack, NULL));
    assert(memcmp(tinted, clear_copy, sizeof(tinted)) == 0);
}

static void test_shaded_ft4_with_classified_transparency_and_abr(void) {
    VhCanvas canvas = {framebuffer, FB_STRIDE, FB_W, FB_H};
    VhFt4Point face[4] = {{1, 1}, {17, 1}, {17, 17}, {1, 17}};
    VhFt4Vertex gpu[4];
    VhPs1AbrState abr = {VH_PS1_ABR_ADD, 1, unpack, pack, NULL};
    VhMap02LightRgb light = {64, 128, 96};
    size_t visible = 0;
    assert(vh_ft4_from_face_perimeter(face, 0, 0, 15, 15, gpu));
    for (size_t y = 0; y < H; ++y) {
        for (size_t x = 0; x < W; ++x) {
            const size_t i = y * W + x;
            source[y * STRIDE + x] = pack(248, (uint8_t)(x * 16),
                                           (uint8_t)(y * 16), NULL);
            masks[i] = i % 11 == 0 ? VH_PS1_TEXEL_TRANSPARENT :
                       i % 5 == 0 ? VH_PS1_TEXEL_STP : VH_PS1_TEXEL_OPAQUE;
            visible += masks[i] != VH_PS1_TEXEL_TRANSPARENT;
        }
    }
    assert(vh_map02_tint_crop_rgba32(
        source, STRIDE, tinted, STRIDE, W, H, light, unpack, pack, NULL));
    for (size_t k = 0; k < FB_STRIDE * FB_H; ++k) framebuffer[k] = BACK;
    assert(vh_canvas_draw_ft4_classified_rgba32(
        &canvas, tinted, W, H, STRIDE, gpu, masks, W,
        vh_ps1_abr_stp_blend, &abr) == visible);
    for (size_t y = 0; y < FB_H; ++y) {
        for (size_t x = 0; x < FB_STRIDE; ++x) {
            uint32_t expected = BACK;
            if (x >= 1 && x <= 16 && y >= 1 && y <= 16) {
                const size_t tx = x - 1, ty = y - 1, i = ty * W + tx;
                const uint32_t shaded = tinted[ty * STRIDE + tx];
                if (masks[i] == VH_PS1_TEXEL_OPAQUE) expected = shaded;
                if (masks[i] == VH_PS1_TEXEL_STP)
                    expected = vh_ps1_abr_stp_blend(BACK, shaded, &abr);
            }
            assert(framebuffer[y * FB_STRIDE + x] == expected);
        }
    }
}

int main(void) {
    test_distance_shade_matches_original_integer_formula();
    test_side_light_table_and_overhead_are_different();
    test_texture_rgb_modulation_and_buffer_integrity();
    test_shaded_ft4_with_classified_transparency_and_abr();
    puts("MAP02 terrain lighting with FT4/ABR tests passed");
    return 0;
}
