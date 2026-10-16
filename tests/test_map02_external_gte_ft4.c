#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_external_gte_ft4.h"

/* Entirely synthetic fixtures: no real MAP02 camera, VRAM or gameplay. */
enum { OT=1024, STRIDE=64, WIDTH=56, HEIGHT=48, COUNT=3 };
static uint8_t decoded[VH_MAP02_EXTERNAL_DECODED_BYTES];
static uint8_t atlas[256*128];
static uint8_t red_clut[32], green_clut[32], blue_clut[32];
static uint32_t pixels[STRIDE*HEIGHT], scratch[256];
static uint8_t classes[256];
static size_t ot_heads[OT];
static VhMap02OtTerrainNode nodes[COUNT];
static VhMap02ExternalFaceEvidence evidence[COUNT];
static VhMap02ExternalPreparedFace prepared[COUNT];
static const uint32_t BG=0x33445566u;

static void le16(uint8_t *p,size_t off,int v) {
    uint16_t u=(uint16_t)v;
    p[off]=(uint8_t)u;
    p[off+1]=(uint8_t)(u>>8);
}
static uint8_t *cell(int z,int x) {
    return decoded+((size_t)z*28u+(size_t)x)*304u;
}
static void set_vertex(uint8_t *tile,unsigned i,int x,int y,int z) {
    le16(tile,(size_t)i*8u,x);
    le16(tile,(size_t)i*8u+2u,y);
    le16(tile,(size_t)i*8u+4u,z);
}
static void set_cell(int z,int x,int height,int count) {
    uint8_t *tile=cell(z,x);
    tile[302]=(uint8_t)count;
    for (int face=0;face<count;++face) {
        le16(tile,176u+2u*(size_t)face,241); /* intentionally identical gfx */
        tile[284u+(size_t)face]=(uint8_t)(4+face);
        for (int i=0;i<4;++i)
            tile[212u+(size_t)face*4u+(size_t)i]=(uint8_t)(face*4+i);
        set_vertex(tile,(unsigned)(face*4),0,0,height);
        set_vertex(tile,(unsigned)(face*4+1),32,0,height);
        set_vertex(tile,(unsigned)(face*4+2),32,32,height);
        set_vertex(tile,(unsigned)(face*4+3),0,32,height);
    }
}
static VhMap02ExternalFaceEvidence observed(int z,int x,int face,int otz) {
    VhMap02ExternalFaceEvidence v={0};
    uint8_t *tile=cell(z,x);
    v.z=z;v.x=x;v.record_index=z*28+x;v.face_index=face;
    v.local_gfx=vh_map02_quad_s16(tile,176u+2u*(size_t)face);
    v.face_shade=tile[284u+(size_t)face];
    v.raw_otz=otz;
    v.u=0;v.v=0;v.w=15;v.h=15;
    for(unsigned i=0;i<4u;++i) {
        int vi=tile[212u+(size_t)face*4u+i];
        v.vertex_indices[i]=vi;
        for(unsigned j=0;j<3u;++j)
            v.vertex_xyz[i][j]=vh_map02_quad_s16(tile,(size_t)vi*8u+j*2u);
    }
    v.perimeter_xy[0][0]=20;v.perimeter_xy[0][1]=20;
    v.perimeter_xy[1][0]=36;v.perimeter_xy[1][1]=20;
    v.perimeter_xy[2][0]=36;v.perimeter_xy[2][1]=36;
    v.perimeter_xy[3][0]=20;v.perimeter_xy[3][1]=36;
    return v;
}
static uint32_t pack(uint8_t r,uint8_t g,uint8_t b,void *unused) {
    (void)unused;
    return UINT32_C(0xff000000) | (uint32_t)r<<16 |
           (uint32_t)g<<8 | b;
}
static void setup(void) {
    memset(decoded,0,sizeof decoded);
    memset(atlas,0,sizeof atlas);
    memset(red_clut,0,sizeof red_clut);
    memset(green_clut,0,sizeof green_clut);
    memset(blue_clut,0,sizeof blue_clut);
    for (size_t y=0;y<16u;++y)
        for(size_t x=0;x<8u;++x)
            atlas[y*128u+x]=0x11u;
    le16(red_clut,2,31);
    le16(green_clut,2,31<<5);
    le16(blue_clut,2,31<<10);
    set_cell(8,19,512,2);
    set_cell(11,11,768,1);
    evidence[0]=observed(8,19,0,128);
    evidence[1]=observed(11,11,0,192);
    evidence[2]=observed(8,19,1,128);
    for(size_t i=0;i<STRIDE*HEIGHT;++i) pixels[i]=BG;
}

static void test_matching_provenance_and_ot_pixels(void) {
    VhMap02OtTerrainScene scene;
    VhCanvas canvas={pixels,STRIDE,WIDTH,HEIGHT};
    size_t n=123,p=456;
    setup();
    assert(vh_map02_prepare_external_batch(decoded,sizeof decoded,
                                           evidence,COUNT,OT,prepared,COUNT));
    assert(prepared[0].z==8 && prepared[0].x==19 &&
           prepared[0].record_index==243 && prepared[0].face_index==0);
    assert(prepared[2].record_index==prepared[0].record_index &&
           prepared[2].face_index==1);
    assert(prepared[0].quad.material==prepared[2].quad.material);
    assert(prepared[0].quad.shade!=prepared[2].quad.shade);
    assert(prepared[0].supplied_gte_observation);
    assert(prepared[0].quad.projection.visible);
    assert(prepared[0].quad.projection.nclip_mac0==0); /* unknown, not computed */
    assert(prepared[0].quad.projection.sz[0]==0);
    assert(prepared[0].quad.projection.otz==128);
    assert(prepared[1].quad.projection.otz==192);
    assert(prepared[0].quad.projection.ot_slot==896u);
    assert(prepared[1].quad.projection.ot_slot==832u);
    assert(prepared[0].quad.gpu_ft4[0].x==20 &&
           prepared[0].quad.gpu_ft4[0].y==20);
    assert(prepared[0].quad.gpu_ft4[1].x==36 &&
           prepared[0].quad.gpu_ft4[1].y==20);
    assert(prepared[0].quad.gpu_ft4[2].x==20 &&
           prepared[0].quad.gpu_ft4[2].y==36);
    assert(prepared[0].quad.gpu_ft4[3].x==36 &&
           prepared[0].quad.gpu_ft4[3].y==36);
    assert(prepared[0].quad.gpu_ft4[0].u==0 &&
           prepared[0].quad.gpu_ft4[3].u==15);
    assert(vh_map02_ot_scene_init(&scene,ot_heads,OT,nodes,COUNT));
    assert(vh_map02_ot_scene_add(&scene,&prepared[0].quad,atlas,sizeof atlas,
                                red_clut,sizeof red_clut,NULL,NULL)==2);
    assert(vh_map02_ot_scene_add(&scene,&prepared[1].quad,atlas,sizeof atlas,
                                green_clut,sizeof green_clut,NULL,NULL)==2);
    assert(vh_map02_ot_scene_add(&scene,&prepared[2].quad,atlas,sizeof atlas,
                                blue_clut,sizeof blue_clut,NULL,NULL)==2);
    assert(vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,256u,
                                  pack,NULL,&n,&p));
    assert(n==3 && p==3u*256u);
    assert(pixels[25*STRIDE+25]==0xffff0000u); /* far green, blue, then near red */
    assert(pixels[19*STRIDE+25]==BG);
    assert(pixels[25*STRIDE+WIDTH]==BG);
}

static void assert_rejected_without_changes(const VhMap02ExternalFaceEvidence *bad,
                                             size_t map_size) {
    VhMap02ExternalPreparedFace out={0};
    out.z=-75;out.quad.material=-321;
    assert(!vh_map02_prepare_external_face(decoded,map_size,bad,OT,&out));
    assert(out.z==-75 && out.quad.material==-321);
}
static void test_mutations_refuse_misattribution(void) {
    VhMap02ExternalFaceEvidence e;
    setup();
    e=evidence[0];e.record_index++;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.face_index=1;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.vertex_indices[1]=4;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.vertex_xyz[1][0]++;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.local_gfx=242;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.face_shade++;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.z=11;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.x=24;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.perimeter_xy[0][0]=1024;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.perimeter_xy[0][0]=-1025;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.raw_otz=-1;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.raw_otz=65536;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.raw_otz=1025;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.u=250;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];e.face_shade=26;assert_rejected_without_changes(&e,sizeof decoded);
    e=evidence[0];assert_rejected_without_changes(&e,sizeof decoded-1);
    e=evidence[0];assert_rejected_without_changes(&e,sizeof decoded+1);
    e=evidence[0];le16(cell(8,19),176,0);
    assert_rejected_without_changes(&e,sizeof decoded);
    setup();
    e=evidence[0];cell(8,19)[302]=19;
    assert_rejected_without_changes(&e,sizeof decoded);
}

static void test_batch_atomic_and_duplicate_keys(void) {
    VhMap02ExternalPreparedFace dest[COUNT];
    VhMap02ExternalFaceEvidence batch[COUNT];
    setup();
    memcpy(batch,evidence,sizeof batch);
    memset(dest,0,sizeof dest);
    dest[0].z=-93;dest[1].z=-93;dest[2].z=-93;
    batch[2]=evidence[0]; /* same face key, even with identical GFX */
    assert(!vh_map02_prepare_external_batch(decoded,sizeof decoded,
                                            batch,COUNT,OT,dest,COUNT));
    for(size_t i=0;i<COUNT;++i)assert(dest[i].z==-93);
    memcpy(batch,evidence,sizeof batch);
    batch[2].vertex_xyz[0][1]=99;
    assert(!vh_map02_prepare_external_batch(decoded,sizeof decoded,
                                            batch,COUNT,OT,dest,COUNT));
    for(size_t i=0;i<COUNT;++i)assert(dest[i].z==-93);
    assert(!vh_map02_prepare_external_batch(decoded,sizeof decoded,
                                            evidence,COUNT,OT,dest,COUNT-1));
    for(size_t i=0;i<COUNT;++i)assert(dest[i].z==-93);
    assert(vh_map02_prepare_external_batch(decoded,sizeof decoded,
                                           evidence,COUNT,OT,dest,COUNT));
    assert(dest[0].z==8 && dest[1].z==11 && dest[2].face_index==1);
}
int main(void) {
    test_matching_provenance_and_ot_pixels();
    test_mutations_refuse_misattribution();
    test_batch_atomic_and_duplicate_keys();
    puts("MAP02 external source-keyed GTE screen and OTZ -> real CLUT4 FT4 pixel replay passed");
    return 0;
}
