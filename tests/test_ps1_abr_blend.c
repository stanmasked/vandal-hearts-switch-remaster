#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/ps1_abr_blend.h"
#include "../source/ft4_textured_quad.h"

#define FB_WIDTH 20
#define FB_HEIGHT 20
#define FB_STRIDE 24
#define T_WIDTH 16
#define T_HEIGHT 16
#define BACKGROUND UINT32_C(0xff422118)
static uint32_t framebuffer[FB_STRIDE * FB_HEIGHT];
static uint32_t texture[T_WIDTH * T_HEIGHT];
static uint8_t classes[T_WIDTH * T_HEIGHT];

static uint32_t pack(uint8_t red, uint8_t green, uint8_t blue, void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) |
           ((uint32_t)blue << 16) | ((uint32_t)green << 8) | red;
}
static void unpack(uint32_t value, uint8_t *red, uint8_t *green,
                   uint8_t *blue, void *ctx) {
    (void)ctx;
    *red = (uint8_t)value;
    *green = (uint8_t)(value >> 8);
    *blue = (uint8_t)(value >> 16);
}

static uint32_t expected_blend(uint32_t destination, uint32_t foreground,
                               unsigned mode) {
    uint8_t dr, dg, db, fr, fg, fb;
    unpack(destination, &dr, &dg, &db, NULL);
    unpack(foreground, &fr, &fg, &fb, NULL);
    return pack(
        vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(dr >> 3, fr >> 3, mode)),
        vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(dg >> 3, fg >> 3, mode)),
        vh_ps1_5_to_8(vh_ps1_abr_blend_5bit(db >> 3, fb >> 3, mode)), NULL);
}

static void test_exact_5bit_modes_and_saturation(void) {
    assert(vh_ps1_abr_blend_5bit(20, 11, VH_PS1_ABR_AVERAGE) == 15);
    assert(vh_ps1_abr_blend_5bit(31, 31, VH_PS1_ABR_AVERAGE) == 30);
    assert(vh_ps1_abr_blend_5bit(20, 11, VH_PS1_ABR_ADD) == 31);
    assert(vh_ps1_abr_blend_5bit(21, 20, VH_PS1_ABR_ADD) == 31);
    assert(vh_ps1_abr_blend_5bit(2, 20, VH_PS1_ABR_SUBTRACT) == 0);
    assert(vh_ps1_abr_blend_5bit(31, 11, VH_PS1_ABR_SUBTRACT) == 20);
    assert(vh_ps1_abr_blend_5bit(24, 15, VH_PS1_ABR_QUARTER) == 27);
    assert(vh_ps1_abr_blend_5bit(31, 31, VH_PS1_ABR_QUARTER) == 31);
    assert(!vh_ps1_abr_mode_valid(4));
    assert(vh_ps1_abr_blend_5bit(32, 10, VH_PS1_ABR_ADD) == 0);
    assert(vh_ps1_abr_blend_5bit(7, 32, VH_PS1_ABR_ADD) == 0);
    assert(vh_ps1_abr_blend_5bit(7, 10, 4) == 0);
    for (unsigned mode = 0; mode < 4; ++mode) {
        assert(vh_ps1_tpage_abr((uint16_t)(mode << 5)) == mode);
        assert(vh_ps1_tpage_abr((uint16_t)((mode << 5) | 0x8f1f)) ==
               (((mode << 5) | 0x8f1f) >> 5 & 3u));
        for (unsigned back = 0; back < 32; ++back)
            for (unsigned fore = 0; fore < 32; ++fore)
                assert(vh_ps1_abr_blend_5bit(back, fore, mode) <= 31);
    }
}

static void test_abe_gate_and_invalid_state(void) {
    VhPs1AbrState state = {VH_PS1_ABR_ADD, 0, unpack, pack, NULL};
    uint32_t back = pack(123, 45, 60, NULL);
    uint32_t front = pack(67, 89, 120, NULL);
    assert(vh_ps1_abr_stp_blend(back, front, &state) == front);
    state.primitive_semi = 1;
    for (unsigned mode = 0; mode < 4; ++mode) {
        state.abr = (uint8_t)mode;
        assert(vh_ps1_abr_stp_blend(back, front, &state) ==
               expected_blend(back, front, mode));
    }
    state.abr = 4;
    assert(vh_ps1_abr_stp_blend(back, front, &state) == front);
    state.abr = 0;
    state.unpack = NULL;
    assert(vh_ps1_abr_stp_blend(back, front, &state) == front);
    assert(vh_ps1_abr_stp_blend(back, front, NULL) == front);
}

static void test_textured_quad_per_pixel_abe_stp_and_cutout(void) {
    VhCanvas canvas = {framebuffer, FB_STRIDE, FB_WIDTH, FB_HEIGHT};
    VhFt4Point face[4] = {{1, 1}, {17, 1}, {17, 17}, {1, 17}};
    VhFt4Vertex gpu[4];
    VhPs1AbrState state = {0, 1, unpack, pack, NULL};
    size_t visible = 0, flagged = 0;
    assert(vh_ft4_from_face_perimeter(face, 0, 0, 15, 15, gpu));
    for (unsigned i = 0; i < T_WIDTH * T_HEIGHT; ++i) {
        unsigned red5 = (i * 3u + 7u) & 31u;
        unsigned green5 = (i * 7u + 11u) & 31u;
        unsigned blue5 = (i * 11u + 13u) & 31u;
        texture[i] = pack(vh_ps1_5_to_8(red5), vh_ps1_5_to_8(green5),
                          vh_ps1_5_to_8(blue5), NULL);
        classes[i] = (i % 8u == 0) ? VH_PS1_TEXEL_TRANSPARENT :
                     (i % 5u == 0 ? VH_PS1_TEXEL_STP : VH_PS1_TEXEL_OPAQUE);
        visible += classes[i] != VH_PS1_TEXEL_TRANSPARENT;
        flagged += classes[i] == VH_PS1_TEXEL_STP;
    }
    assert(visible && flagged);
    for (unsigned mode = 0; mode < 4; ++mode) {
        for (unsigned abe = 0; abe <= 1; ++abe) {
            state.abr = (uint8_t)mode;
            state.primitive_semi = (uint8_t)abe;
            for (unsigned i = 0; i < FB_STRIDE * FB_HEIGHT; ++i)
                framebuffer[i] = BACKGROUND;
            size_t written = vh_canvas_draw_ft4_classified_rgba32(
                &canvas, texture, T_WIDTH, T_HEIGHT, T_WIDTH, gpu,
                classes, T_WIDTH, vh_ps1_abr_stp_blend, &state);
            assert(written == visible);
            for (unsigned y = 0; y < FB_HEIGHT; ++y) {
                for (unsigned x = 0; x < FB_STRIDE; ++x) {
                    uint32_t expected = BACKGROUND;
                    if (x >= 1 && x < 17 && y >= 1 && y < 17) {
                        unsigned i = (y - 1) * 16u + x - 1;
                        if (classes[i] == VH_PS1_TEXEL_OPAQUE ||
                            (classes[i] == VH_PS1_TEXEL_STP && !abe)) {
                            expected = texture[i];
                        } else if (classes[i] == VH_PS1_TEXEL_STP) {
                            expected = expected_blend(BACKGROUND, texture[i], mode);
                        }
                    }
                    assert(framebuffer[y * FB_STRIDE + x] == expected);
                }
            }
        }
    }
}

int main(void) {
    test_exact_5bit_modes_and_saturation();
    test_abe_gate_and_invalid_state();
    test_textured_quad_per_pixel_abe_stp_and_cutout();
    puts("PS1 ABR four-mode FT4 tests passed");
    return 0;
}
