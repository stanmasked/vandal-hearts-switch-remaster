#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_captured_vram4_bridge.h"

/* Invented MAP02/GTE/VRAM evidence; this test is NOT a real game capture. */
enum { N = 3, OT = 1024, W = 64, H = 64, STRIDE = 68, SCRATCH = 256 };
static uint8_t decoded[VH_MAP02_SOURCE_DECODED_BYTES];
static uint8_t vram[VH_MAP02_VRAM_BYTES];
static VhMap02Vram4FrameFace submissions[N];
static size_t heads[OT];
static VhMap02OtTerrainNode nodes[N];
static VhMap02ExternalPreparedFace prepared[N];
static uint8_t atlases[N * VH_MAP02_VRAM4_ATLAS_BYTES];
static uint8_t palettes[N * VH_MAP02_VRAM4_CLUT_BYTES];
static VhMap02Vram4PageStats stats[N];
static uint32_t framebuffer[H * STRIDE], scratch[SCRATCH];
static uint8_t classes[SCRATCH];
static const uint32_t BG = UINT32_C(0x10101010);

static void word(uint8_t *data, size_t index, int value) {
    data[2u * index] = (uint8_t)value;
    data[2u * index + 1u] = (uint8_t)((unsigned)value >> 8);
}

static void make_tile(unsigned record, int two_faces, int material) {
    const size_t offset = (size_t)record * VH_MAP02_FACE_RECORD_BYTES;
    const int xyz[4][3] = {
        {0,0,512},{32,0,512},{32,32,512},{0,32,512}
    };
    for (unsigned i = 0u; i < 4u; ++i) {
        decoded[offset + 212u + i] = (uint8_t)i;
        for (unsigned axis = 0u; axis < 3u; ++axis)
            word(decoded, (offset + i * 8u + axis * 2u) / 2u,
                 xyz[i][axis]);
    }
    decoded[offset + 302u] = (uint8_t)(two_faces ? 2 : 1);
    decoded[offset + 284u] = 7u;
    word(decoded, (offset + 176u) / 2u, material);
    if (two_faces) {
        const uint8_t reverse[4] = {0u,3u,2u,1u};
        memcpy(decoded + offset + 216u, reverse, 4u);
        word(decoded, (offset + 178u) / 2u, 497);
        decoded[offset + 285u] = 19u;
    }
}

static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera c = {0};
    c.rt[0][0] = c.rt[1][1] = c.rt[2][2] = 4096;
    c.ofx = c.ofy = 20 << 16;
    c.h = c.zsf4 = 256;
    return c;
}

static void fixture(VhMap02SourceFaceRequest requests[N],
                    VhMap02CapturedFaceProjection observations[N],
                    VhMap02CapturedTextureState textures[N]) {
    VhMap02ProjectCamera a = camera(), b = camera();
    const int16_t expected_xy[2][4][2] = {
        {{20,20},{36,20},{20,36},{36,36}},
        {{36,20},{52,20},{36,36},{52,36}}
    };
    memset(decoded, 0, sizeof decoded);
    memset(vram, 0, sizeof vram);
    memset(requests, 0, N * sizeof requests[0]);
    memset(observations, 0, N * sizeof observations[0]);
    memset(textures, 0, N * sizeof textures[0]);
    make_tile(59u, 1, 241);
    make_tile(60u, 0, 243);
    b.tr[0] = 32;
    requests[0] = (VhMap02SourceFaceRequest){2,3,59,0,a,0,0,15,15};
    requests[1] = (VhMap02SourceFaceRequest){2,4,60,0,b,16,0,15,15};
    requests[2] = (VhMap02SourceFaceRequest){2,3,59,1,a,32,16,15,15};
    for (unsigned i = 0u; i < N; ++i) {
        VhMap02CapturedFaceProjection *o = &observations[i];
        o->frame = o->camera_frame = 42u;
        o->z = requests[i].z;
        o->x = requests[i].x;
        o->record_index = requests[i].record_index;
        o->face_index = requests[i].face_index;
        textures[i].frame = 42u;
        textures[i].registers =
            (VhMap02Vram4Registers){(int)i,31936+(int)i,0,0,0,0};
    }
    for (unsigned i = 0u; i < 2u; ++i) {
        observations[i].nclip_mac0 = 256;
        observations[i].visible = 1u;
        observations[i].raw_otz = 128;
        memcpy(observations[i].gpu_xy, expected_xy[i],
               sizeof expected_xy[i]);
    }
    observations[2].nclip_mac0 = -256;
    observations[2].raw_otz = -1;
    /* Entire pages contain index 1. The palette is at VRAM row 499. */
    for (unsigned y = 0u; y < 256u; ++y)
        for (unsigned x = 0u; x < 128u; ++x)
            word(vram, (size_t)y*1024u+x, 0x1111);
    word(vram, 499u * 1024u + 1u, 0x001f);
    word(vram, 499u * 1024u + 17u, 0x03e0);
    for (size_t i = 0u; i < H * STRIDE; ++i)
        framebuffer[i] = BG;
}

static uint32_t pack(uint8_t red, uint8_t green, uint8_t blue, void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) | ((uint32_t)red << 16) |
           ((uint32_t)green << 8) | (uint32_t)blue;
}

static VhMap02Vram4FrameWorkspace workspace(void) {
    VhMap02Vram4FrameWorkspace w = {0};
    w.bucket_heads = heads;
    w.bucket_capacity = OT;
    w.nodes = nodes;
    w.prepared = prepared;
    w.atlases = atlases;
    w.atlas_capacity_bytes = sizeof atlases;
    w.palettes = palettes;
    w.palette_capacity_bytes = sizeof palettes;
    w.stats = stats;
    w.face_capacity = N;
    return w;
}

static void test_verified_capture_flows_to_vram4_and_ot(void) {
    VhMap02SourceFaceRequest requests[N];
    VhMap02CapturedFaceProjection observations[N];
    VhMap02CapturedTextureState textures[N];
    VhMap02Vram4FrameInput input = {0};
    VhMap02Vram4FrameWorkspace w = workspace();
    VhCanvas canvas = {framebuffer,STRIDE,W,H};
    size_t count = 99u, drawn = 99u, pixels = 99u;
    fixture(requests,observations,textures);
    assert(vh_map02_stage_captured_vram4_faces(
        decoded,sizeof decoded,requests,observations,textures,
        N,OT,submissions,N,&count));
    assert(count == 2u);
    assert(submissions[0].face.record_index == 59);
    assert(submissions[1].face.record_index == 60);
    assert(submissions[0].face.face_index == 0);
    assert(submissions[1].face.local_gfx == 243);
    assert(submissions[0].face.vertex_indices[2] == 2);
    assert(submissions[0].face.vertex_xyz[2][1] == 32);
    assert(submissions[0].face.perimeter_xy[2][0] == 36);
    assert(submissions[1].face.perimeter_xy[3][0] == 36);
    assert(submissions[1].face.u == 16);
    assert(submissions[0].face.raw_otz == 128);
    assert(submissions[0].observation_frame == 42u);
    assert(submissions[1].gpu_register_frame == 42u);
    input.frame = input.vram_snapshot_frame = 42u;
    input.decoded = decoded; input.decoded_bytes = sizeof decoded;
    input.vram_le = vram; input.vram_bytes = sizeof vram;
    input.faces = submissions; input.face_count = count; input.ot_size = OT;
    assert(vh_map02_vram4_frame_preflight(&input,&w));
    assert(vh_map02_vram4_frame_build(&input,&w));
    assert(w.scene.count == 2u && heads[896] == 1u);
    assert(nodes[1].next == 0u && nodes[0].next == SIZE_MAX);
    assert(vh_map02_ot_scene_draw(&w.scene,&canvas,scratch,classes,SCRATCH,
                                  pack,NULL,&drawn,&pixels));
    assert(drawn == 2u && pixels == 512u);
    assert(framebuffer[25u * STRIDE + 25u] == UINT32_C(0xffff0000));
    assert(framebuffer[25u * STRIDE + 45u] == UINT32_C(0xff00ff00));
    assert(framebuffer[25u * STRIDE + 55u] == BG);
}

static void test_mutations_do_not_change_staged_output(void) {
    VhMap02SourceFaceRequest requests[N];
    VhMap02CapturedFaceProjection observations[N];
    VhMap02CapturedTextureState textures[N];
    VhMap02Vram4FrameFace previous[N];
    size_t count = 77u;
    for (unsigned mutation = 0u; mutation < 11u; ++mutation) {
        fixture(requests,observations,textures);
        memset(submissions, 0xa5, sizeof submissions);
        memcpy(previous, submissions, sizeof previous);
        count = 77u;
        switch (mutation) {
        case 0: textures[0].frame++; break;
        case 1: textures[2].frame++; break; /* culled must be same frame */
        case 2: textures[0].registers.tpage |= 128; break;
        case 3: textures[1].registers.clut = -1; break;
        case 4: observations[0].raw_otz++; break;
        case 5: observations[1].gpu_xy[3][0]++; break;
        case 6: requests[1].camera.tr[0] += 32; break; /* observable XY change */
        case 7: decoded[59u * 304u + 302u] = 1; break;
        case 8: observations[0].camera_frame--; break;
        case 9: requests[1].u = 255; break;
        case 10: textures[0].registers.mask_y = 32; break;
        }
        assert(!vh_map02_stage_captured_vram4_faces(
            decoded,sizeof decoded,requests,observations,textures,
            N,OT,submissions,N,&count));
        assert(count == 77u);
        assert(memcmp(submissions,previous,sizeof previous) == 0);
    }
    fixture(requests,observations,textures);
    memset(submissions,0xa5,sizeof submissions);
    memcpy(previous,submissions,sizeof previous);
    count = 77u;
    assert(!vh_map02_stage_captured_vram4_faces(
        decoded,sizeof decoded,requests,observations,textures,
        N,OT,submissions,1u,&count));
    assert(count == 77u);
    assert(memcmp(submissions,previous,sizeof previous) == 0);
    /* There is no drawable submission when only the reversed face is seen. */
    assert(!vh_map02_stage_captured_vram4_faces(
        decoded,sizeof decoded,&requests[2],&observations[2],&textures[2],
        1u,OT,submissions,N,&count));
    assert(count == 77u);
    assert(memcmp(submissions,previous,sizeof previous) == 0);
}

int main(void) {
    test_verified_capture_flows_to_vram4_and_ot();
    test_mutations_do_not_change_staged_output();
    puts("MAP02 captured GTE -> source FT4 -> VRAM4 -> OT pixel tests passed");
    return 0;
}
