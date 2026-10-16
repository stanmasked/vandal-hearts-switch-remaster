#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_captured_projection_batch.h"

/* All source bytes, screenshots and cameras in this fixture are invented. */
static uint8_t map[VH_MAP02_SOURCE_DECODED_BYTES];

static void put16(size_t offset, int value) {
    const uint16_t v = (uint16_t)value;
    map[offset] = (uint8_t)v;
    map[offset + 1u] = (uint8_t)(v >> 8);
}

static void tile(unsigned record, int two_faces, int material) {
    const size_t at = (size_t)record * VH_MAP02_FACE_RECORD_BYTES;
    static const int p[4][3] = {
        {0,0,512},{32,0,512},{32,32,512},{0,32,512}
    };
    for (unsigned i = 0u; i < 4u; ++i) {
        map[at + 212u + i] = (uint8_t)i;
        for (unsigned axis = 0u; axis < 3u; ++axis)
            put16(at + i*8u + axis*2u, p[i][axis]);
    }
    map[at + 302u] = (uint8_t)(two_faces ? 2 : 1);
    map[at + 284u] = 7u;
    put16(at + 176u, material);
    if (two_faces) {
        static const uint8_t reverse[4] = {0u,3u,2u,1u};
        memcpy(map + at + 216u, reverse, sizeof reverse);
        put16(at + 178u, 497);
        map[at + 285u] = 19u;
    }
}

static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera c = {0};
    c.rt[0][0] = c.rt[1][1] = c.rt[2][2] = 4096;
    c.ofx = c.ofy = 20 << 16;
    c.h = c.zsf4 = 256;
    return c;
}

static void fixture(VhMap02SourceFaceRequest requests[3],
                    VhMap02CapturedFaceProjection observations[3]) {
    VhMap02ProjectCamera a = camera(), b = camera();
    memset(map, 0, sizeof map);
    memset(requests, 0, 3u * sizeof *requests);
    memset(observations, 0, 3u * sizeof *observations);
    tile(59u, 1, 241);
    tile(60u, 0, 243);
    b.tr[0] = 32;
    requests[0] = (VhMap02SourceFaceRequest){2,3,59,0,a,0,0,15,15};
    requests[1] = (VhMap02SourceFaceRequest){2,4,60,0,b,16,0,15,15};
    requests[2] = (VhMap02SourceFaceRequest){2,3,59,1,a,32,16,15,15};

    for (unsigned i = 0u; i < 3u; ++i) {
        observations[i].frame = 42u;
        observations[i].camera_frame = 42u;
        observations[i].z = requests[i].z;
        observations[i].x = requests[i].x;
        observations[i].record_index = requests[i].record_index;
        observations[i].face_index = requests[i].face_index;
    }
    observations[0].nclip_mac0 = observations[1].nclip_mac0 = 256;
    observations[0].visible = observations[1].visible = 1u;
    observations[0].raw_otz = observations[1].raw_otz = 128;
    const int16_t xy[2][4][2] = {
        {{20,20},{36,20},{20,36},{36,36}},
        {{36,20},{52,20},{36,36},{52,36}}
    };
    memcpy(observations[0].gpu_xy, xy[0], sizeof xy[0]);
    memcpy(observations[1].gpu_xy, xy[1], sizeof xy[1]);
    observations[2].nclip_mac0 = -256;
    observations[2].raw_otz = -1; /* NCLIP-culled: no submitted FT4 */
}

static int verify(VhMap02SourceFaceRequest requests[3],
                  VhMap02CapturedFaceProjection obs[3],
                  VhMap02SourceProjectedFace out[3], size_t ot_size) {
    return vh_map02_verify_captured_projection_batch(
        map, sizeof map, requests, obs, 3u, ot_size, out, 3u);
}

static void test_complete_consistent_batch_and_depth_floor(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02CapturedFaceProjection obs[3];
    VhMap02SourceProjectedFace out[3];
    fixture(r, obs);
    memset(out, 0, sizeof out);
    assert(verify(r, obs, out, 1024));
    assert(out[0].record_index == 59 && out[0].quad.material == 241);
    assert(out[1].record_index == 60 && out[1].quad.material == 243);
    assert(out[2].record_index == 59 && out[2].face_index == 1);
    assert(out[2].quad.material == 497 && out[2].quad.shade == 19);
    assert(out[0].quad.drawable && out[1].quad.drawable);
    assert(!out[2].quad.drawable && !out[2].quad.projection.visible);
    assert(out[0].quad.projection.otz == 128);
    assert(out[1].quad.projection.ot_slot == 896);
    assert(out[0].quad.gpu_ft4[1].x == out[1].quad.gpu_ft4[0].x);
    /* A visible AVSZ4 OTZ=0 must still use the renderer depth floor 5. */
    r[0].camera.zsf4 = 0;
    r[1].camera.zsf4 = 0;
    obs[0].raw_otz = obs[1].raw_otz = 0;
    assert(verify(r, obs, out, 5));
    assert(out[0].quad.projection.depth == 5);
    assert(out[1].quad.projection.ot_slot == 0);
}

static void test_mutations_are_rejected_without_partial_output(void) {
    VhMap02SourceFaceRequest r[3];
    VhMap02CapturedFaceProjection obs[3];
    VhMap02SourceProjectedFace out[3], unchanged[3];
    for (unsigned mutation = 0u; mutation < 16u; ++mutation) {
        fixture(r, obs);
        memset(out, 0xa5, sizeof out);
        memcpy(unchanged, out, sizeof out);
        switch (mutation) {
        case 0: obs[2].camera_frame = 41; break;
        case 1: obs[1].frame = 43; break;
        case 2: obs[0].frame = 0; break;
        case 3: obs[1].record_index = 59; break;
        case 4: obs[2].face_index = 0; break;
        case 5: obs[1].nclip_mac0++; break;
        case 6: obs[0].raw_otz++; break;
        case 7: obs[1].gpu_xy[3][1]++; break;
        case 8: obs[2].raw_otz = 0; break;
        case 9: obs[2].gpu_xy[0][0] = 1; break;
        case 10: obs[2].visible = 1; break;
        case 11: obs[0].visible = 2; break;
        case 12: r[1].camera.tr[0] += 32; break;
        case 13: map[59u*304u + 285u] = 26; break;
        case 14: put16(60u*304u + 176u, 0); break;
        case 15: r[2].face_index = 2; break;
        }
        assert(!verify(r, obs, out, 1024));
        assert(memcmp(out, unchanged, sizeof out) == 0);
    }
    fixture(r, obs);
    memset(out, 0xa5, sizeof out);
    memcpy(unchanged, out, sizeof out);
    assert(!verify(r, obs, out, 127)); /* observed visible OTZ out of OT */
    assert(!vh_map02_verify_captured_projection_batch(
        map, sizeof map - 1u, r, obs, 3u, 1024, out, 3u));
    assert(!vh_map02_verify_captured_projection_batch(
        map, sizeof map, r, obs, 3u, 1024, out, 2u));
    assert(!vh_map02_verify_captured_projection_batch(
        map, sizeof map, r, obs, 0u, 1024, out, 3u));
    assert(memcmp(out, unchanged, sizeof out) == 0);
}

int main(void) {
    test_complete_consistent_batch_and_depth_floor();
    test_mutations_are_rejected_without_partial_output();
    puts("MAP02 captured source-keyed GTE FT4 projection batch tests passed");
    return 0;
}
