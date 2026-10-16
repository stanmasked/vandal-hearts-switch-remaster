#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../source/map02_vram4_page.h"
#include "../source/map02_external_gte_ft4.h"

/* No user game resource is linked: VRAM and terrain are synthetic. */
enum { OT=1024, W=56, H=48, STRIDE=60 };
static uint8_t vram[VH_MAP02_VRAM_BYTES];
static uint8_t atlas[VH_MAP02_VRAM4_ATLAS_BYTES+2];
static uint8_t palette[VH_MAP02_VRAM4_CLUT_BYTES+2];
static uint8_t decoded[VH_MAP02_EXTERNAL_DECODED_BYTES];
static uint32_t framebuffer[H*STRIDE], scratch[256];
static uint8_t classes[256];
static size_t buckets[OT];
static VhMap02OtTerrainNode nodes[2];
static unsigned stp_calls;
static const uint32_t CLEAR=0x12345678u;

static void le16(uint8_t *p,size_t i,int v) {
    p[i]=(uint8_t)v;
    p[i+1u]=(uint8_t)((unsigned)v>>8);
}
static void word(unsigned x,unsigned y,uint16_t value) {
    assert(x<1024 && y<512);
    le16(vram,((size_t)y*1024u+x)*2u,(int)value);
}
static uint8_t nibble(const uint8_t *a,unsigned u,unsigned v) {
    assert(u<256 && v<256);
    return (uint8_t)((a[(size_t)v*128u+(u>>1u)] >>
                      ((u&1u)*4u))&15u);
}
static uint32_t pack(uint8_t r,uint8_t g,uint8_t b,void *ctx) {
    (void)ctx;
    return UINT32_C(0xff000000) | ((uint32_t)r<<16u) |
           ((uint32_t)g<<8u) | (uint32_t)b;
}
static uint32_t blend(uint32_t dst,uint32_t src,void *ctx) {
    (void)ctx;
    ++stp_calls;
    return dst ^ src;
}
static void fixture(void) {
    unsigned x,y;
    memset(vram,0,sizeof vram);
    memset(decoded,0,sizeof decoded);
    memset(atlas,0xCC,sizeof atlas);
    memset(palette,0xDD,sizeof palette);
    for(size_t i=0;i<H*STRIDE;++i) framebuffer[i]=CLEAR;
    stp_calls=0;
    /* tpage=5: base word x=320, y=0, 4 texels per VRAM word. */
    for(y=0;y<256;++y)
        for(x=320;x<384;++x)
            word(x,y,0x1111u); /* CLUT entry 1 */
    word(380,192,0x3210u); /* local u=240..243 -> 0,1,2,3 */
    word(382,200,0x4444u); /* texture-window alternate */
    /* clut=31978: (42*16,499) = (672,499). */
    word(672,499,0x0000u);
    word(673,499,0x801fu); /* red STP */
    word(674,499,0x03e0u); /* green opaque */
    word(675,499,0x7c00u); /* blue opaque */
    word(676,499,0x4210u); /* window alternate */
}
static VhMap02Vram4Registers regs(void) {
    VhMap02Vram4Registers r={5,31978,0,0,0,0};
    return r;
}
static void assert_unchanged(void) {
    assert(atlas[0]==0xCCu && atlas[10]==0xCCu &&
           atlas[VH_MAP02_VRAM4_ATLAS_BYTES]==0xCCu);
    assert(palette[0]==0xDDu && palette[10]==0xDDu &&
           palette[VH_MAP02_VRAM4_CLUT_BYTES]==0xDDu);
}

static void test_source_page_nibbles_clut_and_guards(void) {
    VhMap02Vram4PageStats stats={0};
    VhMap02Vram4Registers r=regs();
    fixture();
    assert(vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
              VH_MAP02_VRAM4_ATLAS_BYTES,palette,
              VH_MAP02_VRAM4_CLUT_BYTES,&stats));
    assert(stats.decoded_texels==65536u);
    assert(stats.zero_index_texels==1u);
    assert(stats.stp_palette_texels==65533u);
    assert(stats.page_word_x==320 && stats.page_word_y==0);
    assert(stats.clut_word_x==672 && stats.clut_word_y==499);
    assert(nibble(atlas,240,192)==0u);
    assert(nibble(atlas,241,192)==1u);
    assert(nibble(atlas,242,192)==2u);
    assert(nibble(atlas,243,192)==3u);
    assert(nibble(atlas,244,192)==1u);
    assert(nibble(atlas,255,207)==1u);
    assert(nibble(atlas,248,200)==4u);
    assert((uint16_t)(palette[2] | ((unsigned)palette[3]<<8))==0x801fu);
    assert((uint16_t)(palette[4] | ((unsigned)palette[5]<<8))==0x03e0u);
    assert((uint16_t)(palette[6] | ((unsigned)palette[7]<<8))==0x7c00u);
    assert(atlas[VH_MAP02_VRAM4_ATLAS_BYTES]==0xCCu);
    assert(atlas[VH_MAP02_VRAM4_ATLAS_BYTES+1]==0xCCu);
    assert(palette[VH_MAP02_VRAM4_CLUT_BYTES]==0xDDu);
    assert(palette[VH_MAP02_VRAM4_CLUT_BYTES+1]==0xDDu);
}
static void test_gp0_texture_window_both_axes(void) {
    VhMap02Vram4Registers r=regs();
    fixture();
    r.mask_x=1; r.mask_y=1;
    /* Mask bit 3 of UV on both axes: (248,200)->(240,192). */
    assert(vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert(nibble(atlas,248,200)==0u);
    assert(nibble(atlas,249,200)==1u);
    assert(nibble(atlas,250,200)==2u);
    assert(nibble(atlas,251,200)==3u);
    /* Offset bit 3: (240,192) -> (248,200) and the index 4 word. */
    r.offset_x=1; r.offset_y=1;
    assert(vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert(nibble(atlas,240,192)==4u);
    assert(nibble(atlas,241,192)==4u);
    assert(nibble(atlas,255,207)==1u); /* explicit high-end check */
}
static void test_reject_unsupported_modes_and_bad_storage_atomically(void) {
    VhMap02Vram4Registers r=regs();
    fixture();
    r.tpage|=1<<7; /* 8bpp */
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    r=regs();r.tpage|=2<<7; /* 15bpp */
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    r=regs();r.mask_x=32;
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    r=regs();r.offset_y=-1;
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    r=regs();r.clut=-1;
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    r=regs();
    assert(!vh_map02_vram4_materialize(vram,sizeof vram-2,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES-1,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
    assert(!vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES-1,NULL));
    assert_unchanged();
    assert(!vh_map02_vram4_materialize(NULL,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    assert_unchanged();
}
/* Use the same external source-keyed face adapter as the real submission
 * interface: no inferred camera, source identity must match the tile. */
static VhMap02ExternalPreparedFace prepared_face(void) {
    VhMap02ExternalFaceEvidence e={0};
    VhMap02ExternalPreparedFace out={0};
    uint8_t *tile=decoded+((size_t)8u*28u+19u)*304u;
    tile[302]=1;
    le16(tile,176,241);
    tile[284]=7;
    for(unsigned i=0u;i<4u;++i) tile[212u+i]=(uint8_t)i;
    for(unsigned i=0u;i<4u;++i) {
        unsigned vx=i==1u||i==2u?32u:0u;
        unsigned vy=i>=2u?32u:0u;
        le16(tile,i*8u,(int)vx);
        le16(tile,i*8u+2u,(int)vy);
        le16(tile,i*8u+4u,512);
    }
    e.z=8;e.x=19;e.record_index=8*28+19;e.face_index=0;
    e.local_gfx=241;e.face_shade=7;e.raw_otz=128;
    e.u=240;e.v=192;e.w=15;e.h=15;
    for(unsigned i=0;i<4u;++i) {
        e.vertex_indices[i]=(int32_t)i;
        e.vertex_xyz[i][0]=i==1u||i==2u?32:0;
        e.vertex_xyz[i][1]=i>=2u?32:0;
        e.vertex_xyz[i][2]=512;
    }
    e.perimeter_xy[0][0]=20;e.perimeter_xy[0][1]=20;
    e.perimeter_xy[1][0]=36;e.perimeter_xy[1][1]=20;
    e.perimeter_xy[2][0]=36;e.perimeter_xy[2][1]=36;
    e.perimeter_xy[3][0]=20;e.perimeter_xy[3][1]=36;
    assert(vh_map02_prepare_external_face(decoded,sizeof decoded,&e,OT,&out));
    assert(out.supplied_gte_observation && out.quad.drawable);
    return out;
}
static void test_vram_to_keyed_terrain_ot_and_pixel_output(void) {
    VhMap02Vram4Registers r=regs();
    VhMap02OtTerrainScene scene;
    VhMap02ExternalPreparedFace face;
    VhCanvas screen={framebuffer,STRIDE,W,H};
    size_t drawn=0,pixel_count=0;
    fixture();
    assert(vh_map02_vram4_materialize(vram,sizeof vram,&r,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,NULL));
    face=prepared_face();
    assert(face.record_index==243 && face.face_index==0);
    assert(face.quad.projection.ot_slot==896u);
    assert(vh_map02_ot_scene_init(&scene,buckets,OT,nodes,2u));
    assert(vh_map02_ot_scene_add(&scene,&face.quad,atlas,
        VH_MAP02_VRAM4_ATLAS_BYTES,palette,VH_MAP02_VRAM4_CLUT_BYTES,
        blend,NULL)==2);
    assert(vh_map02_ot_scene_draw(&scene,&screen,scratch,classes,
        256u,pack,NULL,&drawn,&pixel_count));
    assert(drawn==1u && pixel_count==255u);
    assert(stp_calls==253u);
    assert(framebuffer[20*STRIDE+20]==CLEAR);
    assert(framebuffer[20*STRIDE+21]==(CLEAR ^ UINT32_C(0xffff0000)));
    assert(framebuffer[20*STRIDE+22]==UINT32_C(0xff00ff00));
    assert(framebuffer[20*STRIDE+23]==UINT32_C(0xff0000ff));
    assert(framebuffer[20*STRIDE+24]==(CLEAR ^ UINT32_C(0xffff0000)));
    assert(framebuffer[35*STRIDE+35]==(CLEAR ^ UINT32_C(0xffff0000)));
    assert(framebuffer[19*STRIDE+20]==CLEAR);
    assert(framebuffer[25*STRIDE+56]==CLEAR);
}
int main(void) {
    test_source_page_nibbles_clut_and_guards();
    test_gp0_texture_window_both_axes();
    test_reject_unsupported_modes_and_bad_storage_atomically();
    test_vram_to_keyed_terrain_ot_and_pixel_output();
    puts("MAP02 raw VRAM 4bpp tpage/CLUT/texture-window -> source-keyed FT4 frame passed");
    return 0;
}
