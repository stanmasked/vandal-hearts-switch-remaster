#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_vram4_frame.h"

/* Invented frame, source records, GTE observations and texture VRAM. */
enum { N=3, OT=1024, W=56, H=48, STRIDE=60, SCRATCH=256 };
static uint8_t decoded[VH_MAP02_EXTERNAL_DECODED_BYTES];
static uint8_t vram[VH_MAP02_VRAM_BYTES];
static VhMap02Vram4FrameFace observations[N];
static size_t heads[OT];
static VhMap02OtTerrainNode nodes[N];
static VhMap02ExternalPreparedFace prepared[N];
static uint8_t atlases[N * VH_MAP02_VRAM4_ATLAS_BYTES + 2];
static uint8_t palettes[N * VH_MAP02_VRAM4_CLUT_BYTES + 2];
static VhMap02Vram4PageStats stats[N];
static uint32_t fb[H*STRIDE], scratch[SCRATCH];
static uint8_t classes[SCRATCH];
static size_t callback_count;
static const uint32_t BG = UINT32_C(0x10203040);

static void le16(uint8_t *raw, size_t off, int x) {
    raw[off] = (uint8_t)x; raw[off+1] = (uint8_t)((unsigned)x>>8);
}
static void vword(unsigned x,unsigned y,int value) {
    assert(x<1024 && y<512);
    le16(vram,((size_t)y*1024u+x)*2u,value);
}
static uint8_t *cell(unsigned z, unsigned x) {
    return decoded + ((size_t)z*28u+x)*304u;
}
static void build_cell(unsigned z,unsigned x,int face_count,int h) {
    uint8_t *tile=cell(z,x);
    tile[302]=(uint8_t)face_count;
    for(int f=0;f<face_count;++f) {
        le16(tile,176u+2u*(size_t)f,241); /* faces share GFX deliberately */
        tile[284u+(size_t)f]=(uint8_t)(7+f);
        for(int i=0;i<4;++i) {
            unsigned ix=(unsigned)(f*4+i);
            tile[212u+(size_t)f*4u+(size_t)i]=(uint8_t)ix;
            le16(tile,ix*8u,(i==1||i==2)?32:0);
            le16(tile,ix*8u+2u,i>=2?32:0);
            le16(tile,ix*8u+4u,h);
        }
    }
}
static void set_observation(unsigned i,unsigned z,unsigned x,
                            int f,int otz,int tpage,int clut) {
    VhMap02Vram4FrameFace *event=&observations[i];
    VhMap02ExternalFaceEvidence *ev=&event->face;
    uint8_t *tile=cell(z,x);
    memset(event,0,sizeof *event);
    event->observation_frame=411u;
    event->gpu_register_frame=411u;
    event->registers=(VhMap02Vram4Registers){tpage,clut,0,0,0,0};
    ev->z=(int32_t)z;ev->x=(int32_t)x;ev->record_index=(int32_t)(z*28u+x);
    ev->face_index=f;ev->local_gfx=241;ev->face_shade=7+f;
    ev->raw_otz=otz;ev->u=240;ev->v=192;ev->w=15;ev->h=15;
    for (unsigned j=0;j<4u;++j) {
        unsigned ix=(unsigned)(f*4)+(unsigned)j;
        ev->vertex_indices[j]=(int32_t)ix;
        for(unsigned k=0;k<3u;++k)
            ev->vertex_xyz[j][k]=vh_map02_quad_s16(tile,ix*8u+k*2u);
    }
    ev->perimeter_xy[0][0]=20;ev->perimeter_xy[0][1]=20;
    ev->perimeter_xy[1][0]=36;ev->perimeter_xy[1][1]=20;
    ev->perimeter_xy[2][0]=36;ev->perimeter_xy[2][1]=36;
    ev->perimeter_xy[3][0]=20;ev->perimeter_xy[3][1]=36;
}
static uint32_t pack(uint8_t r,uint8_t g,uint8_t b,void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) | ((uint32_t)r<<16) |
           ((uint32_t)g<<8) | b;
}
static uint32_t blend(uint32_t dst,uint32_t src,void *ctx) {
    (void)ctx;
    ++callback_count;
    return dst ^ src;
}
static VhMap02Vram4FrameInput input(void) {
    VhMap02Vram4FrameInput in={0};
    in.frame=411;
    in.vram_snapshot_frame=411;
    in.decoded=decoded;in.decoded_bytes=sizeof decoded;
    in.vram_le=vram;in.vram_bytes=sizeof vram;
    in.faces=observations;in.face_count=N;in.ot_size=OT;
    return in;
}
static VhMap02Vram4FrameWorkspace workspace(void) {
    VhMap02Vram4FrameWorkspace w={0};
    w.bucket_heads=heads;w.bucket_capacity=OT;
    w.nodes=nodes;w.prepared=prepared;
    w.atlases=atlases;w.atlas_capacity_bytes=N*VH_MAP02_VRAM4_ATLAS_BYTES;
    w.palettes=palettes;w.palette_capacity_bytes=N*VH_MAP02_VRAM4_CLUT_BYTES;
    w.stats=stats;w.face_capacity=N;
    return w;
}
static void fixture(void) {
    unsigned x,y;
    memset(decoded,0,sizeof decoded);
    memset(vram,0,sizeof vram);
    memset(observations,0,sizeof observations);
    memset(heads,0,sizeof heads);
    memset(nodes,0,sizeof nodes);
    memset(prepared,0,sizeof prepared);
    memset(stats,0,sizeof stats);
    memset(atlases,0xC7,sizeof atlases);
    memset(palettes,0xD9,sizeof palettes);
    callback_count=0;
    for(size_t i=0;i<H*STRIDE;++i)fb[i]=BG;
    build_cell(8,19,2,512);
    build_cell(11,11,1,768);
    set_observation(0,8,19,0,128,5,31978); /* page5 red opaque */
    set_observation(1,11,11,0,192,7,31980); /* page7 green opaque */
    set_observation(2,8,19,1,128,6,31979); /* page6 blue STP */
    observations[2].blend=blend;
    /* Only the third polygon applies a GP0(E2) window. */
    observations[2].registers.mask_x=1;
    observations[2].registers.mask_y=1;
    observations[2].registers.offset_x=1;
    observations[2].registers.offset_y=1;
    for(y=0;y<256u;++y)for(x=0;x<64u;++x) {
        vword(320+x,y,0x1111);
        vword(384+x,y,0x1111);
        vword(448+x,y,0x1111);
    }
    /* Clut origins: 42*16,43*16,44*16, row499. */
    vword(672+1,499,0x001F);
    vword(688+1,499,0xFC00);
    vword(688+2,499,0x7FFF); /* window-addressed white opaque */
    vword(384+62,200,0x2222); /* effective UV 248..251,200 */
    vword(704+1,499,0x03E0);
}
static void test_all_three_faces_and_per_primitive_vram_state(void) {
    VhMap02Vram4FrameInput in;
    VhMap02Vram4FrameWorkspace w;
    VhCanvas canvas={fb,STRIDE,W,H};
    size_t drawn=99,px=99;
    fixture();
    in=input();w=workspace();
    assert(vh_map02_vram4_frame_preflight(&in,&w));
    assert(vh_map02_vram4_frame_build(&in,&w));
    assert(w.scene.count==N);
    assert(w.scene.heads[832]==1u);
    assert(w.scene.heads[896]==2u);
    assert(w.scene.nodes[2].next==0u); /* same depth, LIFO */
    assert(prepared[0].face_index==0 && prepared[2].face_index==1);
    assert(prepared[0].quad.material==prepared[2].quad.material);
    assert(prepared[0].quad.shade!=prepared[2].quad.shade);
    assert(prepared[1].quad.projection.ot_slot==832u);
    assert(stats[0].decoded_texels==65536u);
    assert(stats[0].stp_palette_texels==0u);
    assert(stats[2].stp_palette_texels==65520u);
    assert(atlases[2*VH_MAP02_VRAM4_ATLAS_BYTES+192u*128u+120u]==0x22u);
    assert(atlases[0*VH_MAP02_VRAM4_ATLAS_BYTES+192u*128u+120u]==0x11u);
    assert((uint16_t)(palettes[2] | ((unsigned)palettes[3]<<8))==0x001fu);
    assert((uint16_t)(palettes[2*32+2] | ((unsigned)palettes[2*32+3]<<8))==0xFC00u);
    assert(atlases[N*VH_MAP02_VRAM4_ATLAS_BYTES]==0xC7u);
    assert(palettes[N*VH_MAP02_VRAM4_CLUT_BYTES]==0xD9u);
    assert(vh_map02_ot_scene_draw(&w.scene,&canvas,scratch,classes,
                                  SCRATCH,pack,NULL,&drawn,&px));
    assert(drawn==N && px==N*256u);
    assert(callback_count==240u);
    /* Far green, near blue STP, then near red opaque (last wins). */
    assert(fb[25*STRIDE+25]==UINT32_C(0xffff0000));
    assert(fb[19*STRIDE+25]==BG);
    assert(fb[25*STRIDE+W]==BG);
    assert(fb[(H-1)*STRIDE+STRIDE-1]==BG);
}
static void outputs_still_pristine(void) {
    assert(heads[0]==0u && nodes[0].quad==NULL);
    assert(prepared[0].quad.drawable==0u);
    assert(stats[0].decoded_texels==0u);
    assert(atlases[0]==0xC7u && atlases[N*VH_MAP02_VRAM4_ATLAS_BYTES]==0xC7u);
    assert(palettes[0]==0xD9u && palettes[N*VH_MAP02_VRAM4_CLUT_BYTES]==0xD9u);
}
static void test_preflight_rejects_cross_frame_and_invalid_metadata_atomically(void) {
    VhMap02Vram4FrameInput in;
    VhMap02Vram4FrameWorkspace w;
    fixture();
    in=input();w=workspace();
    in.vram_snapshot_frame++;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    in=input();observations[2].observation_frame++;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();observations[1].gpu_register_frame--;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.frame=0;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();observations[2].registers.tpage|=128; /* 8-bit */
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();observations[2].registers.clut=-1;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();observations[2].face.vertex_xyz[1][0]++;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();observations[2].face=observations[0].face; /* duplicate */
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.vram_bytes--;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.decoded_bytes--;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();w.atlas_capacity_bytes--;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();w.palette_capacity_bytes--;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();w.bucket_capacity=OT-1u;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();w.face_capacity=N-1u;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.face_count=0;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.ot_size=4u;
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
    fixture();in=input();in.ot_size=64u; /* invalid raw depth */
    assert(!vh_map02_vram4_frame_build(&in,&w));outputs_still_pristine();
}
int main(void) {
    test_all_three_faces_and_per_primitive_vram_state();
    test_preflight_rejects_cross_frame_and_invalid_metadata_atomically();
    puts("MAP02 frame-keyed VRAM4+GTE/FT4 original OT build and atomically rejected mixed frames passed");
    return 0;
}
