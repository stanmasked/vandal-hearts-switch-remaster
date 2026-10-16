#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/ft4_textured_quad.h"

#define TW 256
#define TH 256
#define WIDTH 20
#define HEIGHT 22
#define STRIDE 24
#define CLEAR 0x12345678u
#define GUARD 0xDEADBEEFu

static uint32_t atlas[TW * TH];
static uint32_t framebuffer[STRIDE * HEIGHT];

static VhCanvas canvas(void) {
    VhCanvas c = {framebuffer, STRIDE, WIDTH, HEIGHT};
    return c;
}

static void clear(void) {
    int i;
    for (i = 0; i < STRIDE * HEIGHT; ++i) framebuffer[i] = CLEAR;
    for (i = 0; i < TW * TH; ++i) atlas[i] = GUARD;
}

static void fill_crop(int u, int v) {
    int x, y;
    for (y = 0; y < 16; ++y)
        for (x = 0; x < 16; ++x)
            atlas[(v + y) * TW + u + x] =
                0xff000000u | ((uint32_t)y << 8) | (uint32_t)x;
}

static void make_face(VhFt4Point points[4], float left, float top) {
    points[0] = (VhFt4Point){left, top};
    points[1] = (VhFt4Point){left + 16, top};
    points[2] = (VhFt4Point){left + 16, top + 16};
    points[3] = (VhFt4Point){left, top + 16};
}

static void test_perimeter_wiring_for_both_target_faces(void) {
    const int uv[2][4] = {{240, 192, 15, 15}, {240, 208, 15, 15}};
    VhFt4Point face[4];
    VhFt4Vertex gpu[4];
    VhCanvas c = canvas();
    int target, y, x;
    for (target = 0; target < 2; ++target) {
        int u = uv[target][0], v = uv[target][1];
        clear();
        fill_crop(u, v);
        make_face(face, 1, 2);
        assert(vh_ft4_from_face_perimeter(face, u, v, 15, 15, gpu));
        assert(gpu[0].x == 1 && gpu[0].y == 2);
        assert(gpu[1].x == 17 && gpu[1].y == 2);
        assert(gpu[2].x == 1 && gpu[2].y == 18);
        assert(gpu[3].x == 17 && gpu[3].y == 18);
        assert(gpu[0].u == u && gpu[0].v == v);
        assert(gpu[1].u == u + 15 && gpu[1].v == v);
        assert(gpu[2].u == u && gpu[2].v == v + 15);
        assert(gpu[3].u == u + 15 && gpu[3].v == v + 15);
        assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) >= 256);
        for (y = 0; y < HEIGHT; ++y) {
            for (x = 0; x < STRIDE; ++x) {
                uint32_t got = framebuffer[y * STRIDE + x];
                if (x >= 1 && x < 17 && y >= 2 && y < 18) {
                    uint32_t expected = 0xff000000u |
                        ((uint32_t)(y - 2) << 8) | (uint32_t)(x - 1);
                    assert(got == expected);
                } else {
                    assert(got == CLEAR);
                }
            }
        }
    }
}

static void test_mirrored_world_placement_preserves_corner_attachment(void) {
    VhFt4Point face[4];
    VhFt4Vertex gpu[4];
    VhCanvas c = canvas();
    int x, y;
    clear();
    fill_crop(64, 96);  /* DAT alternative 98: same UVWH size, different crop. */
    make_face(face, 1, 2);
    face[0].x = face[3].x = 17;
    face[1].x = face[2].x = 1;
    assert(vh_ft4_from_face_perimeter(face, 64, 96, 15, 15, gpu));
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) >= 256);
    for (y = 0; y < 16; ++y)
        for (x = 0; x < 16; ++x)
            assert(framebuffer[(y + 2) * STRIDE + x + 1] ==
                   (0xff000000u | ((uint32_t)y << 8) | (uint32_t)(15 - x)));
}

static void test_crop_clipping_and_strides(void) {
    VhFt4Point face[4];
    VhFt4Vertex gpu[4];
    uint32_t tiny_tex[24] = {
        1, 2, 3, 4, GUARD, GUARD,
        5, 6, 7, 8, GUARD, GUARD,
        9, 10, 11, 12, GUARD, GUARD,
        13, 14, 15, 16, GUARD, GUARD
    };
    VhCanvas c = canvas();
    size_t n;
    clear();
    make_face(face, -8, -8);
    assert(vh_ft4_from_face_perimeter(face, 0, 0, 3, 3, gpu));
    n = vh_canvas_draw_ft4_rgba32(&c, tiny_tex, 4, 4, 6, gpu);
    assert(n >= 64);
    assert(framebuffer[0] == 11);   /* viewport upper-left => texel (2,2) */
    assert(framebuffer[7 * STRIDE + 7] == 16);
    assert(framebuffer[0 * STRIDE + 8] == CLEAR);
    assert(framebuffer[8 * STRIDE] == CLEAR);
    assert(framebuffer[0 * STRIDE + WIDTH] == CLEAR);
    assert(framebuffer[(HEIGHT - 1) * STRIDE + STRIDE - 1] == CLEAR);
}

static void test_malformed_geometry_and_bounds_do_not_write(void) {
    VhFt4Point face[4];
    VhFt4Vertex gpu[4];
    VhCanvas c = canvas();
    uint32_t marker[STRIDE * HEIGHT];
    clear();
    fill_crop(240, 192);
    memcpy(marker, framebuffer, sizeof(marker));
    make_face(face, 1, 2);
    face[0].x = NAN;
    assert(!vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    make_face(face, 1, 2);
    assert(!vh_ft4_from_face_perimeter(face, 250, 250, 15, 15, gpu));
    assert(vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    gpu[0].u = NAN;
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
    gpu[0].u = -1.0f;
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
    gpu[0].u = 240.0f;
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, 1, gpu) == 0);
    assert(vh_canvas_draw_ft4_rgba32(&c, NULL, TW, TH, TW, gpu) == 0);
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, NULL) == 0);
    assert(vh_canvas_draw_ft4_rgba32(NULL, atlas, TW, TH, TW, gpu) == 0);
    assert(memcmp(marker, framebuffer, sizeof(marker)) == 0);
}

static void test_degenerate_offscreen_and_huge_coordinates(void) {
    VhFt4Point face[4];
    VhFt4Vertex gpu[4];
    VhCanvas c = canvas();
    size_t n;
    clear();
    fill_crop(240, 192);
    make_face(face, 50000, 50000);
    assert(vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
    make_face(face, 1, 1);
    face[2] = face[1]; /* second triangle can collapse, first remains legal. */
    assert(vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    n = vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu);
    assert(n > 0);
    clear();
    make_face(face, 1, 1);
    face[0].y = face[1].y = face[2].y = face[3].y = 2;
    assert(vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
    make_face(face, 1.0e30f, 1.0e30f);
    assert(vh_ft4_from_face_perimeter(face, 240, 192, 15, 15, gpu));
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
    /* Input with an invalid canvas stride must not touch the allocation. */
    c.stride_pixels = 1;
    assert(vh_canvas_draw_ft4_rgba32(&c, atlas, TW, TH, TW, gpu) == 0);
}

int main(void) {
    test_perimeter_wiring_for_both_target_faces();
    test_mirrored_world_placement_preserves_corner_attachment();
    test_crop_clipping_and_strides();
    test_malformed_geometry_and_bounds_do_not_write();
    test_degenerate_offscreen_and_huge_coordinates();
    puts("FT4 textured quad tests passed");
    return 0;
}
