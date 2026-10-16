#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_face_direction.h"
#include "../source/map02_terrain_lighting.h"

static void write16(uint8_t *tile, size_t offset, int16_t number) {
    tile[offset] = (uint8_t)(uint16_t)number;
    tile[offset + 1] = (uint8_t)((uint16_t)number >> 8);
}
static void vertex(uint8_t *tile, unsigned at, int x, int y, int z) {
    write16(tile, (size_t)at * 8u, (int16_t)x);
    write16(tile, (size_t)at * 8u + 2, (int16_t)y);
    write16(tile, (size_t)at * 8u + 4, (int16_t)z);
}
static void tile_for_vector(uint8_t tile[304], int nx, int ny, int nz) {
    int e1x = 0, e1y = -nz, e1z = ny;
    int e2x, e2y, e2z;
    memset(tile, 0, 304);
    if (!e1y && !e1z) e1z = 1;
    e2x = ny * e1z - nz * e1y;
    e2y = nz * e1x - nx * e1z;
    e2z = nx * e1y - ny * e1x;
    vertex(tile, 0, 0, 0, 0);
    vertex(tile, 1, e1x * 100, e1y * 100, e1z * 100);
    vertex(tile, 2, e2x * 100, e2y * 100, e2z * 100);
    vertex(tile, 3, e2x * 100, e2y * 100, e2z * 100);
    tile[212] = 0; tile[213] = 1; tile[214] = 2; tile[215] = 3;
    tile[302] = 1;
}

static void test_exact_original_26_axes_classify_independently(void) {
    uint8_t tile[304], result;
    VhMap02Cross normal;
    for (unsigned i = 0; i < 26; ++i) {
        VhMap02Direction d = vh_map02_directions[i];
        tile_for_vector(tile, d.x, d.y, d.z);
        result = 255;
        assert(vh_map02_face_direction(tile, sizeof(tile), 0, &result, &normal));
        assert(result == i);
        assert(normal.x || normal.y || normal.z);
        assert(vh_map02_candidate_dot(normal, vh_map02_directions[i]) > 0);
        VhMap02LightRgb directional[26] = {{0, 0, 0}};
        VhMap02LightRgb shaded = {0, 0, 0};
        directional[i] = (VhMap02LightRgb){128, 100, 80};
        assert(vh_map02_select_side_light(directional, 26, result, 278, &shaded));
        assert(shaded.red == 64 && shaded.green == 50 && shaded.blue == 40);
    }
}

static void test_face_indices_and_repeated_vertex_source_branches(void) {
    uint8_t tile[304], idx = 255;
    VhMap02Cross n;
    tile_for_vector(tile, 0, 1, 0);
    /* Source branch var_a1 == var_a0: [0,0,1,2] means
     * first=vertex1, second=vertex0, third=vertex2. */
    tile[212] = 0; tile[213] = 0; tile[214] = 1; tile[215] = 2;
    assert(vh_map02_face_direction(tile, 304, 0, &idx, &n));
    assert(idx == 1); /* reversed orientation -> -Y */
    tile_for_vector(tile, 0, 1, 0);
    tile[212] = 0; tile[213] = 1; tile[214] = 0; tile[215] = 2;
    assert(vh_map02_face_direction(tile, 304, 0, &idx, &n));
    assert(idx == 1);
    tile_for_vector(tile, 0, 1, 0);
    tile[212] = 0; tile[213] = 1; tile[214] = 2; tile[215] = 0;
    assert(vh_map02_face_direction(tile, 304, 0, &idx, &n));
    assert(idx == 1);
    tile_for_vector(tile, 0, 1, 0);
    tile[212] = 0; tile[213] = 1; tile[214] = 1; tile[215] = 2;
    assert(vh_map02_face_direction(tile, 304, 0, &idx, &n));
    assert(idx == 1);
}

static void test_bad_geometry_does_not_modify_outputs(void) {
    uint8_t tile[304], shade = 101;
    VhMap02Cross normal = {99, 88, 77};
    tile_for_vector(tile, 1, 0, 0);
    assert(!vh_map02_face_direction(NULL, 304, 0, &shade, &normal));
    assert(!vh_map02_face_direction(tile, 303, 0, &shade, &normal));
    assert(!vh_map02_face_direction(tile, 304, 0, NULL, &normal));
    assert(!vh_map02_face_direction(tile, 304, 1, &shade, &normal));
    tile[302] = 0;
    assert(!vh_map02_face_direction(tile, 304, 0, &shade, &normal));
    tile[302] = 19;
    assert(!vh_map02_face_direction(tile, 304, 0, &shade, &normal));
    tile[302] = 1;
    tile[212] = 22;
    assert(!vh_map02_face_direction(tile, 304, 0, &shade, &normal));
    tile[212] = 0;
    /* Exact line/point degeneracies must be handled, unlike simple
     * equal-corner checks that can miss collinear polygons. */
    vertex(tile, 0, 0, 0, 0);
    vertex(tile, 1, 100, 0, 0);
    vertex(tile, 2, 200, 0, 0);
    assert(!vh_map02_face_direction(tile, 304, 0, &shade, &normal));
    assert(shade == 101);
    assert(normal.x == 99 && normal.y == 88 && normal.z == 77);
}

static void test_large_signed_vertices_do_not_overflow_cross(void) {
    uint8_t tile[304], result = 255;
    VhMap02Cross normal;
    tile_for_vector(tile, 0, 1, 0);
    vertex(tile, 0, -32768, -32768, -32768);
    vertex(tile, 1, 32767, -32768, -32768);
    vertex(tile, 2, -32768, -32768, 32767);
    assert(vh_map02_face_direction(tile, sizeof(tile), 0, &result, &normal));
    assert(result == 1);
    assert(normal.y == -INT64_C(4294836225));
}

int main(void) {
    test_exact_original_26_axes_classify_independently();
    test_face_indices_and_repeated_vertex_source_branches();
    test_bad_geometry_does_not_modify_outputs();
    test_large_signed_vertices_do_not_overflow_cross();
    puts("MAP02 26-direction face classification tests passed");
    return 0;
}
