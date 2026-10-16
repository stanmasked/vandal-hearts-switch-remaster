#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_projection.h"
#include "../source/map02_face_direction.h"

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
static void test_adjacent_faces_share_projected_edge(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex left[4] = {
        {0,0,512},{100,0,512},{100,100,512},{0,100,512}
    };
    const VhMap02ProjectVertex right[4] = {
        {100,0,512},{200,0,512},{200,100,512},{100,100,512}
    };
    VhMap02ProjectFace a = {0}, b = {0};
    assert(vh_map02_project_face(&c, left, 1024, &a));
    assert(vh_map02_project_face(&c, right, 1024, &b));
    assert(a.visible && b.visible && a.ot_in_bounds && b.ot_in_bounds);
    assert(a.otz == b.otz && a.ot_slot == b.ot_slot);
    /* GPU FT4 order is 0,1,3,2 relative to source perimeter. */
    assert(a.gpu[1].x == b.gpu[0].x && a.gpu[1].y == b.gpu[0].y);
    assert(a.gpu[3].x == b.gpu[2].x && a.gpu[3].y == b.gpu[2].y);
    assert(a.gpu[1].x == 210 && a.gpu[3].y == 170);
    /* Changing depth in only one face destroys shared-screen equality. */
    VhMap02ProjectVertex shifted[4];
    memcpy(shifted, right, sizeof shifted);
    for (unsigned i = 0; i < 4; ++i) shifted[i].z = 768;
    assert(vh_map02_project_face(&c, shifted, 1024, &b));
    assert(b.visible);
    assert(b.otz != a.otz);
    assert(b.gpu[0].x != a.gpu[1].x);
}

static void test_sloped_neighbors_share_gte_screen_endpoints(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex left[4] = {
        {0,0,512},{100,0,640},{100,100,640},{0,100,512}
    };
    const VhMap02ProjectVertex right[4] = {
        {100,0,640},{200,0,640},{200,100,640},{100,100,640}
    };
    VhMap02ProjectFace a = {0}, b = {0};
    assert(vh_map02_project_face(&c, left, 1024, &a));
    assert(vh_map02_project_face(&c, right, 1024, &b));
    assert(a.visible && b.visible);
    /* Match the two *identical* shared 3D endpoints in GPU corner order. */
    assert(a.gpu[1].x == b.gpu[0].x && a.gpu[1].y == b.gpu[0].y);
    assert(a.gpu[3].x == b.gpu[2].x && a.gpu[3].y == b.gpu[2].y);
    /* OTZ is per face: even with a shared edge, depths can differ. */
    assert(a.otz != b.otz);
    assert(a.ot_in_bounds && b.ot_in_bounds);
}

static void test_projection_and_face_lighting_direction(void) {
    VhMap02ProjectCamera c = camera();
    VhMap02ProjectFace projected = {0};
    VhMap02ProjectVertex vertices[4] = {
        {0,0,512}, {100,0,512}, {100,100,512}, {0,100,512}
    };
    uint8_t tile[VH_MAP02_TILE_BYTES] = {0};
    uint8_t direction = 255;
    VhMap02Cross cross = {0};
    tile[302] = 1;
    for (unsigned i = 0; i < 4; ++i) {
        const int16_t xyz[3] = {vertices[i].x, vertices[i].y, vertices[i].z};
        tile[212+i] = (uint8_t)i;
        for (unsigned axis = 0; axis < 3; ++axis) {
            unsigned at = i*8u + axis*2u;
            tile[at] = (uint8_t)((uint16_t)xyz[axis] & 255u);
            tile[at+1] = (uint8_t)(((uint16_t)xyz[axis] >> 8) & 255u);
        }
    }
    assert(vh_map02_face_direction(tile, sizeof tile, 0, &direction, &cross));
    assert(cross.x == 0 && cross.y == 0 && cross.z == 10000);
    assert(direction < VH_MAP02_LIGHT_DIRECTION_COUNT);
    assert(vh_map02_project_face(&c, vertices, 1024, &projected));
    assert(projected.visible && projected.otz == 128);
    /* Reversing face winding changes direction and NCLIP consistently. */
    tile[213] = 3; tile[215] = 1;
    VhMap02ProjectVertex reversed[4] = {
        vertices[0], vertices[3], vertices[2], vertices[1]
    };
    uint8_t opposite = 255;
    assert(vh_map02_face_direction(tile, sizeof tile, 0, &opposite, &cross));
    assert(cross.z == -10000 && opposite != direction);
    assert(vh_map02_project_face(&c, reversed, 1024, &projected));
    assert(!projected.visible && projected.nclip_mac0 < 0);
}

static void test_neighbor_normals_and_projection_in_one_batch(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex vertices[6] = {
        {0,0,512}, {100,0,640}, {100,100,640}, {0,100,512},
        {200,0,640}, {200,100,640}
    };
    const unsigned face_indices[2][4] = {
        {0,1,2,3}, {1,4,5,2}
    };
    uint8_t tile[VH_MAP02_TILE_BYTES] = {0};
    uint8_t shade[2] = {255,255};
    VhMap02Cross normals[2];
    VhMap02ProjectFace projected[2] = {0};
    tile[302] = 2;
    for (unsigned i = 0; i < 6; ++i) {
        const int16_t xyz[3] = {vertices[i].x,vertices[i].y,vertices[i].z};
        for (unsigned axis = 0; axis < 3; ++axis) {
            const unsigned at = i*8u + axis*2u;
            tile[at] = (uint8_t)((uint16_t)xyz[axis] & 255u);
            tile[at+1] = (uint8_t)((uint16_t)xyz[axis] >> 8);
        }
    }
    for (unsigned f = 0; f < 2; ++f) {
        VhMap02ProjectVertex corners[4];
        for (unsigned i = 0; i < 4; ++i) {
            tile[212u + f*4u + i] = (uint8_t)face_indices[f][i];
            corners[i] = vertices[face_indices[f][i]];
        }
        assert(vh_map02_face_direction(tile,sizeof tile,f,&shade[f],&normals[f]));
        assert(vh_map02_project_face(&c,corners,1024,&projected[f]));
        assert(projected[f].visible && projected[f].ot_in_bounds);
    }
    assert(normals[0].x != normals[1].x);
    assert(normals[0].z == normals[1].z);
    assert(shade[0] != shade[1]);
    assert(projected[0].otz != projected[1].otz);
    assert(projected[0].gpu[1].x == projected[1].gpu[0].x);
    assert(projected[0].gpu[1].y == projected[1].gpu[0].y);
    assert(projected[0].gpu[3].x == projected[1].gpu[2].x);
    assert(projected[0].gpu[3].y == projected[1].gpu[2].y);
}

static void test_neighbor_projection_under_camera_translation(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex a[4] = {
        {0,0,512},{100,0,640},{100,100,640},{0,100,512}
    };
    const VhMap02ProjectVertex b[4] = {
        {100,0,640},{200,0,640},{200,100,640},{100,100,640}
    };
    VhMap02ProjectFace p, q;
    for (unsigned step = 0; step < 8; ++step) {
        c.tr[0] = (int32_t)step * 12 - 36;
        c.tr[1] = (int32_t)step * 7 - 20;
        c.tr[2] = (int32_t)step * 16;
        assert(vh_map02_project_face(&c,a,1024,&p));
        assert(vh_map02_project_face(&c,b,1024,&q));
        assert(p.visible && q.visible && p.ot_in_bounds && q.ot_in_bounds);
        assert(p.gpu[1].x == q.gpu[0].x && p.gpu[1].y == q.gpu[0].y);
        assert(p.gpu[3].x == q.gpu[2].x && p.gpu[3].y == q.gpu[2].y);
    }
}

static void test_neighbor_projection_under_quarter_turns(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex a[4] = {
        {0,0,512},{100,0,640},{100,100,640},{0,100,512}
    };
    const VhMap02ProjectVertex b[4] = {
        {100,0,640},{200,0,640},{200,100,640},{100,100,640}
    };
    const int16_t turn[4][4] = {
        {4096,0,0,4096}, {0,4096,-4096,0},
        {-4096,0,0,-4096}, {0,-4096,4096,0}
    };
    VhMap02ProjectFace p = {0}, q = {0};
    for (unsigned i = 0; i < 4; ++i) {
        c.rt[0][0] = turn[i][0]; c.rt[0][2] = turn[i][1];
        c.rt[2][0] = turn[i][2]; c.rt[2][2] = turn[i][3];
        c.tr[2] = 1024;
        assert(vh_map02_project_face(&c,a,4096,&p));
        assert(vh_map02_project_face(&c,b,4096,&q));
        /* Culling may change, but both identical 3D edge endpoints must
         * project identically whenever both faces are front-facing. */
        if (p.visible && q.visible) {
            assert(p.gpu[1].x == q.gpu[0].x && p.gpu[1].y == q.gpu[0].y);
            assert(p.gpu[3].x == q.gpu[2].x && p.gpu[3].y == q.gpu[2].y);
        }
    }
}

static void test_neighbor_projection_under_diagonal_q12_rotations(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex a[4] = {
        {0,0,512},{100,0,640},{100,100,640},{0,100,512}
    };
    const VhMap02ProjectVertex b[4] = {
        {100,0,640},{200,0,640},{200,100,640},{100,100,640}
    };
    /* Rounded fixed-point rotations; these are synthetic camera inputs,
     * not values recovered from the original MAP02 runtime. */
    const int16_t rotations[4][4] = {
        {2896,2896,-2896,2896}, {-2896,2896,-2896,-2896},
        {-2896,-2896,2896,-2896}, {2896,-2896,2896,2896}
    };
    VhMap02ProjectFace p = {0}, q = {0};
    unsigned jointly_visible = 0;
    for (unsigned i = 0; i < 4; ++i) {
        c.rt[0][0] = rotations[i][0]; c.rt[0][2] = rotations[i][1];
        c.rt[2][0] = rotations[i][2]; c.rt[2][2] = rotations[i][3];
        c.tr[2] = 1024;
        assert(vh_map02_project_face(&c,a,4096,&p));
        assert(vh_map02_project_face(&c,b,4096,&q));
        if (p.visible && q.visible) {
            ++jointly_visible;
            assert(p.gpu[1].x == q.gpu[0].x && p.gpu[1].y == q.gpu[0].y);
            assert(p.gpu[3].x == q.gpu[2].x && p.gpu[3].y == q.gpu[2].y);
        }
    }
    assert(jointly_visible > 0);
}

static void test_shared_projection_across_depth_and_screen_clamps(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex a[4] = {
        {0,0,512},{100,0,640},{100,100,640},{0,100,512}
    };
    const VhMap02ProjectVertex b[4] = {
        {100,0,640},{200,0,640},{200,100,640},{100,100,640}
    };
    const int32_t offsets[] = {-640,-512,-256,0,512,4096,30000};
    VhMap02ProjectFace p = {0}, q = {0};
    unsigned compared = 0;
    for (unsigned k = 0; k < sizeof offsets / sizeof offsets[0]; ++k) {
        c.tr[2] = offsets[k];
        assert(vh_map02_project_face(&c,a,65536,&p));
        assert(vh_map02_project_face(&c,b,65536,&q));
        if (p.visible && q.visible) {
            ++compared;
            assert(p.gpu[1].x == q.gpu[0].x && p.gpu[1].y == q.gpu[0].y);
            assert(p.gpu[3].x == q.gpu[2].x && p.gpu[3].y == q.gpu[2].y);
        }
    }
    assert(compared >= 3);
}

static void test_projection_ot_boundaries_and_saturation(void) {
    VhMap02ProjectCamera c = camera();
    const VhMap02ProjectVertex face[4] = {
        {0,0,512},{100,0,512},{100,100,512},{0,100,512}
    };
    VhMap02ProjectFace p = {0};
    assert(vh_map02_project_face(&c,face,128,&p));
    assert(p.visible && p.otz == 128 && p.ot_in_bounds && p.ot_slot == 0);
    assert(vh_map02_project_face(&c,face,127,&p));
    assert(p.visible && !p.ot_in_bounds);
    c.zsf4 = 0;
    assert(vh_map02_project_face(&c,face,5,&p));
    assert(p.visible && p.otz == 0 && p.depth == 5 &&
           p.ot_in_bounds && p.ot_slot == 0);
    assert(vh_map02_project_face(&c,face,4,&p));
    assert(p.visible && !p.ot_in_bounds);
    c = camera();
    c.ofx = 1023 << 16; c.ofy = 1023 << 16;
    VhMap02ProjectSxy xy = {0};
    uint16_t sz = 0;
    uint32_t flags = 0;
    assert(vh_map02_project_vertex(&c,face[2],&xy,&sz,&flags));
    assert(xy.x == 1023 && xy.y == 1023 && sz == 512);
    assert((flags & (1u << 14)) != 0u);
    assert((flags & (1u << 13)) != 0u);
    assert(vh_map02_project_face(&c,face,128,&p));
    /* Saturation collapses every corner to one XY: NCLIP culls it. */
    assert(!p.visible && p.nclip_mac0 == 0);
    assert(!p.ot_in_bounds && p.otz == 0);
    assert((p.rtpt_flags & (1u << 14)) != 0u);
    assert((p.rtpt_flags & (1u << 13)) != 0u);
}

static void test_unr_perspective_division_threshold(void) {
    VhMap02ProjectCamera c = camera();
    VhMap02ProjectSxy xy = {0};
    uint16_t sz = 0;
    uint32_t flags = 0;
    const VhMap02ProjectVertex at_threshold = {10,20,128};
    const VhMap02ProjectVertex just_above = {10,20,129};
    uint32_t dividend = 0;
    assert(vh_map02_proj_unr(256,128,&flags,&dividend));
    assert(dividend == 0x1ffffu);
    assert((flags & (1u << 17)) != 0u);
    flags = 0;
    assert(vh_map02_proj_unr(256,129,&flags,&dividend));
    assert(dividend < 0x1ffffu);
    assert((flags & (1u << 17)) == 0u);
    flags = 0;
    assert(vh_map02_project_vertex(&c,at_threshold,&xy,&sz,&flags));
    assert(sz == 128 && (flags & (1u << 17)) != 0u);
    flags = 0;
    assert(vh_map02_project_vertex(&c,just_above,&xy,&sz,&flags));
    assert(sz == 129 && (flags & (1u << 17)) == 0u);
    flags = 0;
    assert(vh_map02_proj_unr(256,0,&flags,&dividend));
    assert(dividend == 0x1ffffu && (flags & (1u << 17)) != 0u);
}

static void test_unr_threshold_sweep(void) {
    /* Integer-only boundary sweep: saturation begins at H >= 2*SZ,
     * including SZ=0. No empirical camera parameters are assumed. */
    const uint16_t heights[] = {1, 2, 64, 255, 256, 511, 1024, 32767};
    for (unsigned i = 0; i < sizeof heights / sizeof heights[0]; ++i) {
        const uint16_t h = heights[i];
        const uint16_t near = (uint16_t)(h / 2u);
        const uint16_t beyond = (uint16_t)(near + 1u);
        uint32_t flags = 0, quotient = 0;
        assert(vh_map02_proj_unr(h, near, &flags, &quotient));
        assert(quotient == 0x1ffffu && (flags & (1u << 17)) != 0u);
        flags = 0;
        assert(vh_map02_proj_unr(h, beyond, &flags, &quotient));
        assert((flags & (1u << 17)) == 0u);
        assert(quotient <= 0x1ffffu);
    }
}

int main(void) {
    test_screen_quad_and_ordering();
    test_backface_and_zero_area();
    test_perspective_clipping_and_flag_reset();
    test_invalid_input_never_overwrites_output();
    test_adjacent_faces_share_projected_edge();
    test_sloped_neighbors_share_gte_screen_endpoints();
    test_projection_and_face_lighting_direction();
    test_neighbor_normals_and_projection_in_one_batch();
    test_neighbor_projection_under_camera_translation();
    test_neighbor_projection_under_quarter_turns();
    test_neighbor_projection_under_diagonal_q12_rotations();
    test_shared_projection_across_depth_and_screen_clamps();
    test_projection_ot_boundaries_and_saturation();
    test_unr_perspective_division_threshold();
    test_unr_threshold_sweep();
    puts("MAP02 portable projection, NCLIP, AVSZ4 and OT slot tests passed");
    return 0;
}
