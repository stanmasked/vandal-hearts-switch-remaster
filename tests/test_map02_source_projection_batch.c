#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_source_projection_batch.h"

/* Deliberately invented tiles and cameras: no retail MAP02 bytes. */
static uint8_t decoded[VH_MAP02_SOURCE_DECODED_BYTES];

static void put16(size_t offset, int value) {
    uint16_t bits = (uint16_t)value;
    decoded[offset] = (uint8_t)bits;
    decoded[offset + 1u] = (uint8_t)(bits >> 8);
}

static void make_tile(unsigned record, unsigned count, int gfx0) {
    const size_t at = (size_t)record * VH_MAP02_FACE_RECORD_BYTES;
    const int xyz[4][3] = {
        {0,0,512}, {32,0,512}, {32,32,512}, {0,32,512}
    };
    for (unsigned i = 0; i < 4u; ++i) {
        decoded[at + 212u + i] = (uint8_t)i;
        for (unsigned axis = 0; axis < 3u; ++axis)
            put16(at + i*8u + axis*2u, xyz[i][axis]);
    }
    decoded[at + 302u] = (uint8_t)count;
    decoded[at + 284u] = 7;
    put16(at + 176u, gfx0);
    if (count == 2u) {
        for (unsigned i = 0; i < 4u; ++i)
            decoded[at + 216u + i] = (uint8_t)i;
        decoded[at + 285u] = 19;
        put16(at + 178u, 497);
    }
}

static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera c = {0};
    c.rt[0][0] = c.rt[1][1] = c.rt[2][2] = 4096;
    c.h = c.zsf4 = 256;
    c.ofx = 20 << 16;
    c.ofy = 20 << 16;
    return c;
}

static void fixture(VhMap02SourceFaceRequest r[3]) {
    VhMap02ProjectCamera a = camera();
    VhMap02ProjectCamera b = camera();
    memset(decoded, 0, sizeof decoded);
    memset(r, 0, 3u * sizeof *r);
    make_tile(59, 2, 241); /* z=2,x=3, faces 0 and 1 */
    make_tile(60, 1, 243); /* z=2,x=4, face 0 */
    b.tr[0] = 32; /* explicit model-to-camera translation, not grid inference */
    r[0] = (VhMap02SourceFaceRequest){2,3,59,0,a,0,0,15,15};
    r[1] = (VhMap02SourceFaceRequest){2,4,60,0,b,16,0,15,15};
    r[2] = (VhMap02SourceFaceRequest){2,3,59,1,a,32,16,15,15};
}

static void test_source_keys_materials_and_tile_cameras(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02SourceProjectedFace out[3];
    fixture(r);
    memset(out, 0, sizeof out);
    assert(vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(out[0].record_index == 59 && out[0].face_index == 0);
    assert(out[1].record_index == 60 && out[1].face_index == 0);
    assert(out[2].record_index == 59 && out[2].face_index == 1);
    assert(out[0].quad.material == 241 && out[0].quad.shade == 7);
    assert(out[1].quad.material == 243 && out[1].quad.shade == 7);
    assert(out[2].quad.material == 497 && out[2].quad.shade == 19);
    assert(out[0].quad.u == 0 && out[1].quad.u == 16);
    assert(out[2].quad.u == 32 && out[2].quad.v == 16);
    assert(out[0].quad.drawable && out[1].quad.drawable &&
           out[2].quad.drawable);
    assert(out[0].quad.projection.otz == 128 &&
           out[1].quad.projection.otz == 128);
    assert(out[0].quad.gpu_ft4[1].x == out[1].quad.gpu_ft4[0].x);
    assert(out[0].quad.gpu_ft4[1].y == out[1].quad.gpu_ft4[0].y);
    assert(out[0].quad.gpu_ft4[3].x == out[1].quad.gpu_ft4[2].x);
    assert(out[0].quad.gpu_ft4[3].y == out[1].quad.gpu_ft4[2].y);
    assert(out[0].quad.gpu_ft4[0].x == out[2].quad.gpu_ft4[0].x);

    /* Independent camera Z translation changes only the second tile. */
    r[1].camera.tr[2] = 256;
    assert(vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(out[0].quad.projection.otz == 128);
    assert(out[1].quad.projection.otz == 192);
    assert(out[2].quad.projection.otz == 128);
}

static void test_rejects_invalid_batch_without_partial_writes(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02SourceProjectedFace out[3], previous[3];
    fixture(r);
    memset(out, 0x5a, sizeof out);
    memcpy(previous, out, sizeof out);
    r[2].record_index = 60;
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
    fixture(r);
    r[2] = r[0]; /* duplicate exact source face */
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
    fixture(r);
    r[2].face_index = 2; /* source faceCt=2, valid slots 0 and 1 */
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
    fixture(r);
    r[2].x = 24; /* outside 24 active cells, though stride is 28 */
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
    fixture(r);
    decoded[59u * 304u + 216u] = 22; /* invalid vertex on last face */
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
    fixture(r);
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded - 1u, r, 3, 1024, out, 3));
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 2));
    assert(!vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 0, 1024, out, 3));
    assert(memcmp(out, previous, sizeof out) == 0);
}

static void test_null_material_keeps_source_identity_but_does_not_draw(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02SourceProjectedFace out[3];
    fixture(r);
    put16(60u * 304u + 176u, 0);
    /* GFX_NULL matches the PC renderer's early skip before vertex reads. */
    decoded[60u * 304u + 212u] = 255;
    assert(vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(out[1].quad.material == 0 && !out[1].quad.drawable);
    assert(out[1].record_index == 60 && out[1].face_index == 0);
    assert(out[0].quad.drawable && out[2].quad.drawable);
}


static void test_multicell_batch_preserves_pc_ordering_table_insertion(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02SourceProjectedFace out[3];
    VhMap02OtTerrainScene scene;
    size_t heads[1024];
    VhMap02OtTerrainNode nodes[3];
    static uint8_t atlas[32768], palette[32];
    fixture(r);
    assert(vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(vh_map02_ot_scene_init(&scene, heads, 1024, nodes, 3));
    for (unsigned i = 0; i < 3u; ++i)
        assert(vh_map02_ot_scene_add(
            &scene, &out[i].quad, atlas, sizeof atlas,
            palette, sizeof palette, NULL, NULL) == 2);
    /* All at depth 128: original AddPrim inserts at bucket head. */
    assert(scene.count == 3u && heads[896] == 2u);
    assert(nodes[2].next == 1u && nodes[1].next == 0u);
    assert(nodes[0].next == SIZE_MAX);

    r[1].camera.tr[2] = 256; /* only second cell moves in camera Z */
    assert(vh_map02_project_source_batch(
        decoded, sizeof decoded, r, 3, 1024, out, 3));
    assert(vh_map02_ot_scene_init(&scene, heads, 1024, nodes, 3));
    for (unsigned i = 0; i < 3u; ++i)
        assert(vh_map02_ot_scene_add(
            &scene, &out[i].quad, atlas, sizeof atlas,
            palette, sizeof palette, NULL, NULL) == 2);
    /* Farther face is drawn from lower OT bucket; same-depth faces LIFO. */
    assert(out[1].quad.projection.otz == 192);
    assert(heads[832] == 1u && nodes[1].next == SIZE_MAX);
    assert(heads[896] == 2u && nodes[2].next == 0u);
    assert(nodes[0].next == SIZE_MAX);
}

int main(void) {
    test_source_keys_materials_and_tile_cameras();
    test_rejects_invalid_batch_without_partial_writes();
    test_null_material_keeps_source_identity_but_does_not_draw();
    test_multicell_batch_preserves_pc_ordering_table_insertion();
    puts("MAP02 source-keyed multi-cell GTE/FT4 batch tests passed");
    return 0;
}
