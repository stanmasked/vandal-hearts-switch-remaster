#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_projection.h"

static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera c = {0};
    c.rt[0][0] = c.rt[1][1] = c.rt[2][2] = 4096;
    c.h = 256;
    c.zsf4 = 256;
    c.ofx = 160 << 16;
    c.ofy = 120 << 16;
    return c;
}
static void test_screen_quad_and_ordering(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex face[4] = {
        {0,0,512},{100,0,512},{100,100,512},{0,100,512}
    };
    VhMap02ProjectFace result = {0};
    assert(vh_map02_project_face(&c, face, 1024, &result));
    assert(result.visible);
    assert(result.nclip_mac0 == 2500);
    assert(result.gpu[0].x == 160 && result.gpu[0].y == 120);
    assert(result.gpu[1].x == 210 && result.gpu[1].y == 120);
    assert(result.gpu[2].x == 160 && result.gpu[2].y == 170);
    assert(result.gpu[3].x == 210 && result.gpu[3].y == 170);
    for (unsigned i = 0; i < 4; ++i) assert(result.sz[i] == 512);
    assert(result.otz == 128 && result.depth == 128);
    assert(result.ot_slot == 896 && result.ot_in_bounds);
    assert(result.rtpt_flags == 0 && result.rtps_flags == 0);
    assert(vh_map02_project_face(&c, face, 64, &result));
    assert(result.visible && !result.ot_in_bounds);
}
static void test_backface_and_zero_area(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex reverse[4] = {
        {0,0,512},{0,100,512},{100,100,512},{100,0,512}
    };
    VhMap02ProjectVertex same[4] = {
        {0,0,512},{0,0,512},{0,0,512},{0,0,512}
    };
    VhMap02ProjectFace result;
    assert(vh_map02_project_face(&c, reverse, 1024, &result));
    assert(!result.visible && result.nclip_mac0 < 0);
    assert(!result.ot_in_bounds && result.otz == 0);
    assert(vh_map02_project_face(&c, same, 1024, &result));
    assert(!result.visible && result.nclip_mac0 == 0);
}
static void test_perspective_clipping_and_flag_reset(void) {
    VhMap02ProjectCamera c = camera();
    VhMap02ProjectSxy pos = {0};
    uint16_t sz = 65535;
    uint32_t flags = 0;
    VhMap02ProjectVertex near_point = {3000, -3000, 0};
    assert(vh_map02_project_vertex(&c, near_point, &pos, &sz, &flags));
    assert(sz == 0 && (flags & (UINT32_C(1) << 17)));
    assert(pos.x == 1023 && pos.y == -1024);
    assert(flags & (1u << 14));
    assert(flags & (1u << 13));
    assert(vh_map02_proj_wrap32(INT64_C(4294967295)) == -1);
    assert(vh_map02_proj_wrap32(-INT64_C(4294967295)) == 1);
    assert(vh_map02_proj_asr(-1, 12) == -1);
    assert(vh_map02_proj_asr(-4096, 12) == -1);
    assert(vh_map02_proj_asr(-4097, 12) == -2);
    assert(vh_map02_proj_satu16(-10) == 0);
    assert(vh_map02_proj_satu16(70000) == 65535);
}
static void test_invalid_input_never_overwrites_output(void) {
    VhMap02ProjectCamera c = camera();
    VhMap02ProjectVertex verts[4] = {
        {0,0,512},{100,0,512},{100,100,512},{0,100,512}
    };
    VhMap02ProjectFace marker = {0};
    marker.nclip_mac0 = 12345;
    marker.depth = 222;
    assert(!vh_map02_project_face(NULL, verts, 1024, &marker));
    assert(!vh_map02_project_face(&c, NULL, 1024, &marker));
    assert(!vh_map02_project_face(&c, verts, 1024, NULL));
    assert(marker.nclip_mac0 == 12345 && marker.depth == 222);
}
int main(void) {
    test_screen_quad_and_ordering();
    test_backface_and_zero_area();
    test_perspective_clipping_and_flag_reset();
    test_invalid_input_never_overwrites_output();
    puts("MAP02 portable projection, NCLIP, AVSZ4 and OT slot tests passed");
    return 0;
}
