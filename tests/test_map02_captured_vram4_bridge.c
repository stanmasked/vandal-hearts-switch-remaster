#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_captured_vram4_bridge.h"
#include "../source/map02_vram4_timeline_frame.h"
#include "../source/map02_vram4_transfer_ledger.h"
#include "../source/map02_vram4_transfer_import.h"

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


static uint8_t later_vram[VH_MAP02_VRAM_BYTES];

static VhMap02Vram4TimelineInput timeline_input(
    const VhMap02Vram4TimelineEntry entries[2]) {
    VhMap02Vram4TimelineInput input = {0};
    input.frame = 42u;
    input.decoded = decoded;
    input.decoded_bytes = sizeof decoded;
    input.entries = entries;
    input.count = 2u;
    input.ot_size = OT;
    return input;
}

static void timeline_fixture(VhMap02Vram4TimelineEntry entries[2]) {
    VhMap02SourceFaceRequest requests[N];
    VhMap02CapturedFaceProjection observations[N];
    VhMap02CapturedTextureState textures[N];
    size_t count = 0u;
    fixture(requests,observations,textures);
    /* Same texture page and CLUT for both polygons, different sampled
     * VRAM content at each submitted primitive's acquisition instant. */
    textures[1].registers = textures[0].registers;
    assert(vh_map02_stage_captured_vram4_faces(
        decoded,sizeof decoded,requests,observations,textures,
        N,OT,submissions,N,&count));
    assert(count == 2u);
    memcpy(later_vram,vram,sizeof vram);
    word(later_vram,499u * 1024u + 1u,0x03e0);
    for (unsigned i=0u; i<2u; ++i) {
        entries[i] = (VhMap02Vram4TimelineEntry){0};
        entries[i].face = submissions[i];
        entries[i].vram_le = i == 0u ? vram : later_vram;
        entries[i].vram_bytes = VH_MAP02_VRAM_BYTES;
        entries[i].vram_snapshot_frame = 42u;
        entries[i].submission_index = i;
        entries[i].vram_snapshot_index = i;
    }
}

static void clear_timeline_workspace(void) {
    memset(heads,0,sizeof heads);
    memset(nodes,0,sizeof nodes);
    memset(prepared,0,sizeof prepared);
    memset(stats,0,sizeof stats);
    memset(atlases,0xa5,sizeof atlases);
    memset(palettes,0x5a,sizeof palettes);
    for (size_t i=0u; i<H*STRIDE; ++i)
        framebuffer[i] = BG;
}

static void assert_timeline_workspace_unmodified(void) {
    assert(heads[0] == 0u && heads[896] == 0u);
    assert(nodes[0].quad == NULL);
    assert(prepared[0].quad.drawable == 0u);
    assert(stats[0].decoded_texels == 0u);
    assert(atlases[0] == 0xa5u && palettes[0] == 0x5au);
}

static void test_timeline_detects_clut_change_between_submissions(void) {
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w = workspace();
    VhCanvas canvas = {framebuffer,STRIDE,W,H};
    size_t drawn = 0u, pixels = 0u;
    timeline_fixture(entries);
    clear_timeline_workspace();
    input = timeline_input(entries);
    assert(vh_map02_vram4_timeline_preflight(&input,&w));
    assert(vh_map02_vram4_timeline_build(&input,&w));
    assert(w.scene.count == 2u);
    assert(w.scene.heads[896] == 1u && nodes[1].next == 0u);
    assert((uint16_t)(palettes[2] | ((unsigned)palettes[3]<<8)) == 0x001fu);
    assert((uint16_t)(palettes[32+2] | ((unsigned)palettes[32+3]<<8)) == 0x03e0u);
    assert(vh_map02_ot_scene_draw(&w.scene,&canvas,scratch,classes,SCRATCH,
                                  pack,NULL,&drawn,&pixels));
    assert(drawn == 2u && pixels == 512u);
    assert(framebuffer[25u*STRIDE+25u] == UINT32_C(0xffff0000));
    assert(framebuffer[25u*STRIDE+45u] == UINT32_C(0xff00ff00));
    assert(framebuffer[25u*STRIDE+55u] == BG);
}

static void test_timeline_invalid_snapshots_fail_before_output(void) {
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w = workspace();
    for (unsigned mutation=0u; mutation<9u; ++mutation) {
        timeline_fixture(entries);
        clear_timeline_workspace();
        input=timeline_input(entries);
        switch (mutation) {
        case 0: entries[1].vram_snapshot_frame = 43u; break;
        case 1: entries[1].submission_index = 0u; break;
        case 2: entries[1].vram_snapshot_index = 0u; break;
        case 3: entries[1].vram_bytes -= 1u; break;
        case 4: entries[0].vram_le = NULL; break;
        case 5: entries[1].face.gpu_register_frame = 43u; break;
        case 6: entries[1].face.face = entries[0].face.face; break;
        case 7: entries[1].face.registers.tpage |= 128; break;
        case 8: input.frame = 43u; break;
        }
        assert(!vh_map02_vram4_timeline_preflight(&input,&w));
        assert(!vh_map02_vram4_timeline_build(&input,&w));
        assert_timeline_workspace_unmodified();
    }
    timeline_fixture(entries);
    clear_timeline_workspace();
    input=timeline_input(entries);
    w.palette_capacity_bytes=VH_MAP02_VRAM4_CLUT_BYTES;
    assert(!vh_map02_vram4_timeline_build(&input,&w));
    assert_timeline_workspace_unmodified();
}


static uint8_t ledger_replay[VH_MAP02_VRAM_BYTES];

static VhMap02VramTransfer clut_clear_event(void) {
    VhMap02VramTransfer ev = {0};
    ev.frame = 42u;
    ev.step = 0u;
    ev.before_submission = 1u;
    ev.operation = VH_MAP02_VRAM_OP_CLEAR;
    ev.x = 1; ev.y = 499; ev.w = 1; ev.h = 1;
    ev.green = 248; /* BGR555 0x03e0: same observed CLUT mutation */
    return ev;
}

static void test_transfer_ledger_gates_pixels_and_missing_writes(void) {
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w = workspace();
    VhMap02VramTransfer clear = clut_clear_event();
    VhCanvas canvas = {framebuffer,STRIDE,W,H};
    size_t drawn = 0u, pixels = 0u;
    timeline_fixture(entries);
    clear_timeline_workspace();
    input = timeline_input(entries);

    /* The changed CLUT cannot be silently attributed to an unlogged GPU
     * operation, even though both per-face GTE and VRAM snapshots are valid. */
    assert(!vh_map02_vram4_timeline_build_with_ledger(
        &input,&w,NULL,0u,ledger_replay,sizeof ledger_replay));
    assert_timeline_workspace_unmodified();

    assert(vh_map02_vram4_timeline_verify_ledger(
        &input,&w,&clear,1u,ledger_replay,sizeof ledger_replay));
    assert(vh_map02_vram4_timeline_build_with_ledger(
        &input,&w,&clear,1u,ledger_replay,sizeof ledger_replay));
    assert(w.scene.count == 2u && heads[896] == 1u);
    assert((uint16_t)(palettes[2] | ((unsigned)palettes[3]<<8)) == 0x001fu);
    assert((uint16_t)(palettes[32+2] |
                      ((unsigned)palettes[32+3]<<8)) == 0x03e0u);
    assert(vh_map02_ot_scene_draw(&w.scene,&canvas,scratch,classes,SCRATCH,
                                  pack,NULL,&drawn,&pixels));
    assert(drawn == 2u && pixels == 512u);
    assert(framebuffer[25u*STRIDE+25u] == UINT32_C(0xffff0000));
    assert(framebuffer[25u*STRIDE+45u] == UINT32_C(0xff00ff00));
}

static void test_transfer_ledger_mutations_leave_renderer_untouched(void) {
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w = workspace();
    const uint8_t green[2] = {0xe0u,0x03u};
    for (unsigned mutation=0u; mutation<14u; ++mutation) {
        VhMap02VramTransfer ev = clut_clear_event();
        timeline_fixture(entries);
        clear_timeline_workspace();
        input=timeline_input(entries);
        switch (mutation) {
        case 0: ev.frame = 41u; break;
        case 1: ev.step = 1u; break;
        case 2: ev.before_submission = 0u; break;
        case 3: ev.before_submission = 2u; break;
        case 4: ev.green = 224; break; /* wrong observed CLUT color */
        case 5: ev.x = 2; break;       /* wrong palette address */
        case 6: ev.operation = 99; break;
        case 7: ev.w = 0; break;
        case 8: ev.w = 2048; ev.h = 2048; break;
        case 9: ev.operation = VH_MAP02_VRAM_OP_LOAD;
                ev.load_le = green; ev.load_bytes = 1u; break;
        case 10: ev.operation = VH_MAP02_VRAM_OP_MOVE;
                 ev.dest_x = 0; ev.dest_y = 0; break;
        case 11: entries[1].vram_snapshot_frame++; break;
        case 12: entries[1].vram_snapshot_index = 0u; break;
        case 13: word(later_vram, 400u * 1024u + 15u, 0x7c00);
                 break; /* unrelated VRAM mutation is still unexplained */
        }
        assert(!vh_map02_vram4_timeline_build_with_ledger(
            &input,&w,&ev,1u,ledger_replay,sizeof ledger_replay));
        assert_timeline_workspace_unmodified();
    }
    timeline_fixture(entries);
    clear_timeline_workspace();
    input=timeline_input(entries);
    VhMap02VramTransfer ev=clut_clear_event();
    assert(!vh_map02_vram4_timeline_build_with_ledger(
        &input,&w,&ev,1u,ledger_replay,sizeof ledger_replay-1u));
    assert_timeline_workspace_unmodified();
    /* Complete identical VRAM snapshots require zero transfer events. */
    entries[1].vram_le = entries[0].vram_le;
    assert(vh_map02_vram4_timeline_verify_ledger(
        &input,&w,NULL,0u,ledger_replay,sizeof ledger_replay));
}

static void test_transfer_ledger_source_copy_semantics(void) {
    VhMap02VramTransfer ev = {0};
    const uint8_t payload[4] = {0x1fu,0x00u,0xe0u,0x03u};
    memset(ledger_replay,0,sizeof ledger_replay);
    ev.frame=42u; ev.step=0u; ev.before_submission=1u;
    ev.operation=VH_MAP02_VRAM_OP_LOAD;
    ev.x=-1; ev.y=0; ev.w=2; ev.h=1;
    ev.load_le=payload; ev.load_bytes=sizeof payload;
    assert(vh_map02_vram_ledger_event_valid(&ev,0u,42u,2u));
    vh_map02_vram_ledger_apply(ledger_replay,&ev);
    assert(vh_map02_vram_ledger_read(ledger_replay,0u)==0x03e0u);
    ev=(VhMap02VramTransfer){0};
    ev.frame=42u; ev.step=0u; ev.before_submission=1u;
    ev.operation=VH_MAP02_VRAM_OP_MOVE;
    ev.x=10;ev.y=12;ev.w=3;ev.h=1;
    ev.dest_x=11;ev.dest_y=12;
    for(unsigned x=10u;x<14u;++x)
        vh_map02_vram_ledger_write(
            ledger_replay,12u*1024u+x,(uint16_t)(x-9u));
    assert(vh_map02_vram_ledger_event_valid(&ev,0u,42u,2u));
    vh_map02_vram_ledger_apply(ledger_replay,&ev);
    /* PC MoveImage copies in-place from left to right, not memmove. */
    for(unsigned x=10u;x<14u;++x)
        assert(vh_map02_vram_ledger_read(
            ledger_replay,12u*1024u+x)==1u);
}


static void packet_u32(uint8_t *data, size_t at, uint32_t value) {
    for (unsigned b=0u; b<4u; ++b)
        data[at+b] = (uint8_t)(value >> (b*8u));
}

static void packet_fixture(uint8_t packet[84]) {
    memset(packet,0,84u);
    memcpy(packet,"VHMAPGL1",8u);
    packet_u32(packet,8u,42u);  /* frame */
    packet_u32(packet,12u,2u); /* submissions */
    packet_u32(packet,16u,1u); /* transfer count */
    packet_u32(packet,20u,84u); /* total length */
    packet_u32(packet,32u+4u,1u); /* before submission 1 */
    packet_u32(packet,32u+8u,VH_MAP02_VRAM_OP_CLEAR);
    packet_u32(packet,32u+12u,1u); /* x=1 */
    packet_u32(packet,32u+16u,499u); /* y=499 */
    packet_u32(packet,32u+20u,1u); /* w */
    packet_u32(packet,32u+24u,1u); /* h */
    packet_u32(packet,32u+40u,248u); /* green, BGR555 0x03e0 */
}

static void test_private_transfer_packet_import_and_draw(void) {
    uint8_t packet[84];
    VhMap02VramTransfer events[2];
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w=workspace();
    VhCanvas canvas={framebuffer,STRIDE,W,H};
    size_t count=77u,drawn=0u,pixels=0u;
    packet_fixture(packet);
    timeline_fixture(entries);
    clear_timeline_workspace();
    input=timeline_input(entries);
    assert(vh_map02_vram_ledger_import_packet(
        packet,sizeof packet,42u,2u,events,2u,&count));
    assert(count==1u);
    assert(events[0].operation==VH_MAP02_VRAM_OP_CLEAR);
    assert(events[0].step==0u && events[0].before_submission==1u);
    assert(events[0].x==1 && events[0].y==499 && events[0].green==248);
    assert(vh_map02_vram4_timeline_build_from_packet(
        &input,&w,packet,sizeof packet,events,2u,
        ledger_replay,sizeof ledger_replay));
    assert(vh_map02_ot_scene_draw(&w.scene,&canvas,scratch,classes,SCRATCH,
                                  pack,NULL,&drawn,&pixels));
    assert(drawn==2u && pixels==512u);
    assert(framebuffer[25u*STRIDE+25u]==UINT32_C(0xffff0000));
    assert(framebuffer[25u*STRIDE+45u]==UINT32_C(0xff00ff00));
}

static void test_private_transfer_packet_corruption_is_atomic(void) {
    uint8_t packet[88];
    VhMap02VramTransfer events[2], unchanged[2];
    VhMap02Vram4TimelineEntry entries[2];
    VhMap02Vram4TimelineInput input;
    VhMap02Vram4FrameWorkspace w=workspace();
    for (unsigned mutation=0u; mutation<15u; ++mutation) {
        size_t count=73u,bytes=84u;
        packet_fixture(packet);
        timeline_fixture(entries);
        clear_timeline_workspace();
        input=timeline_input(entries);
        memset(events,0xa5,sizeof events);
        memcpy(unchanged,events,sizeof events);
        switch(mutation) {
        case 0: packet[0]='!'; break;
        case 1: packet_u32(packet,8u,41u); break; /* wrong frame */
        case 2: packet_u32(packet,12u,3u); break; /* wrong submission count */
        case 3: packet_u32(packet,16u,2u); break; /* missing event */
        case 4: packet_u32(packet,20u,85u); break; /* length mismatch */
        case 5: packet[24]=1u; break; /* nonzero reserved header */
        case 6: packet_u32(packet,32u,1u); break; /* invalid step */
        case 7: packet_u32(packet,36u,0u); break; /* invalid boundary */
        case 8: packet_u32(packet,40u,99u); break; /* unsupported op */
        case 9: packet_u32(packet,60u,3u); break; /* nonzero unused dest x */
        case 10: packet_u32(packet,80u,2u); break; /* nonzero payload length */
        case 11: packet_u32(packet,52u,0u); break; /* zero width */
        case 12: packet_u32(packet,72u,256u); break; /* invalid green */
        case 13: packet_u32(packet,32u+52u-4u,40000u); break;
        case 14: bytes=83u; break; /* truncated record */
        }
        assert(!vh_map02_vram_ledger_import_packet(
            packet,bytes,42u,2u,events,2u,&count));
        assert(count==73u);
        assert(memcmp(events,unchanged,sizeof events)==0);
        assert(!vh_map02_vram4_timeline_build_from_packet(
            &input,&w,packet,bytes,events,2u,
            ledger_replay,sizeof ledger_replay));
        assert_timeline_workspace_unmodified();
    }
    packet_fixture(packet);
    timeline_fixture(entries);
    clear_timeline_workspace();
    input=timeline_input(entries);
    packet_u32(packet,44u,2u); /* wrong X: valid packet, bad VRAM replay */
    assert(!vh_map02_vram4_timeline_build_from_packet(
        &input,&w,packet,84u,events,2u,
        ledger_replay,sizeof ledger_replay));
    assert_timeline_workspace_unmodified();
}

int main(void) {
    test_verified_capture_flows_to_vram4_and_ot();
    test_mutations_do_not_change_staged_output();
    test_timeline_detects_clut_change_between_submissions();
    test_timeline_invalid_snapshots_fail_before_output();
    test_transfer_ledger_gates_pixels_and_missing_writes();
    test_transfer_ledger_mutations_leave_renderer_untouched();
    test_transfer_ledger_source_copy_semantics();
    test_private_transfer_packet_import_and_draw();
    test_private_transfer_packet_corruption_is_atomic();
    puts("MAP02 captured GTE -> source FT4 -> VRAM4 -> OT pixel tests passed");
    return 0;
}
