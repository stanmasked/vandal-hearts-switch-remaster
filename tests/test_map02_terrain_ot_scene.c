#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/map02_terrain_ot_scene.h"

/* No retail MAP02 vertices, camera, palettes or textures in these tests. */
enum { OT=1024, WIDTH=56, HEIGHT=48, STRIDE=64, MAXNODES=4 };
static size_t heads[OT];
static VhMap02OtTerrainNode nodes[MAXNODES];
static uint8_t tile[304];
static uint8_t atlas[256*128];
static uint8_t red_clut[32], green_clut[32], blue_clut[32];
static uint32_t fb[STRIDE*HEIGHT], scratch[16*16];
static uint8_t classes[16*16];
static VhMap02TerrainQuad a, b, c;
static uint32_t observed[4];
static size_t observations;
static const uint32_t CLEAR = 0x10203040u;
static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera m={0};
    m.rt[0][0]=m.rt[1][1]=m.rt[2][2]=4096;
    m.ofx=20<<16;
    m.ofy=20<<16;
    m.h=256;
    m.zsf4=256;
    return m;
}
static void le16(uint8_t *dst, size_t at, uint16_t v) {
    dst[at]=(uint8_t)v;
    dst[at+1]=(uint8_t)(v>>8);
}
static void setup_tile(int z) {
    memset(tile,0,sizeof tile);
    le16(tile,176,241);
    tile[212]=0;tile[213]=1;tile[214]=2;tile[215]=3;
    tile[302]=1;
    for(unsigned i=0;i<4u;++i) {
        int x=(i==1u||i==2u)?32:0;
        int y=(i==2u||i==3u)?32:0;
        le16(tile,i*8u,(uint16_t)x);
        le16(tile,i*8u+2u,(uint16_t)y);
        le16(tile,i*8u+4u,(uint16_t)z);
    }
}
static uint32_t pack(uint8_t r,uint8_t g,uint8_t bl,void *context) {
    (void)context;
    return UINT32_C(0xff000000) | ((uint32_t)r<<16) |
           ((uint32_t)g<<8) | bl;
}
static uint32_t observe_stp(uint32_t dst,uint32_t src,void *context) {
    (void)dst;
    (void)context;
    if (observations==0 || observed[observations-1]!=src) {
        assert(observations < 4u);
        observed[observations++]=src;
    }
    return src;
}
static void setup(void) {
    VhMap02ProjectCamera m=camera();
    memset(atlas,0,sizeof atlas);
    for(unsigned y=0;y<16u;++y)
        for(unsigned x=0;x<8u;++x)
            atlas[y*128u+x]=0x11u; /* every pixel is STP index 1 */
    memset(red_clut,0,sizeof red_clut);
    memset(green_clut,0,sizeof green_clut);
    memset(blue_clut,0,sizeof blue_clut);
    le16(red_clut,2,0x801fu);
    le16(green_clut,2,0x83e0u);
    le16(blue_clut,2,0xfc00u);
    for(size_t k=0;k<STRIDE*HEIGHT;++k) fb[k]=CLEAR;
    observations=0;
    memset(observed,0,sizeof observed);
    setup_tile(512);
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&m,OT,
                                         0,0,15,15,&a));
    b=a; /* another material/quad at exactly the same OT depth */
    b.material=242;
    setup_tile(768);
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&m,OT,
                                         0,0,15,15,&c));
    assert(a.drawable && b.drawable && c.drawable);
    assert(a.projection.depth==128 && a.projection.ot_slot==896u);
    assert(c.projection.depth==192 && c.projection.ot_slot==832u);
}
static int enqueue(VhMap02OtTerrainScene *scene,
                   const VhMap02TerrainQuad *q,const uint8_t clut[32]) {
    return vh_map02_ot_scene_add(scene,q,atlas,sizeof atlas,
                                 clut,32,observe_stp,NULL);
}
static void test_depth_and_lifo_bucket_order(void) {
    VhMap02OtTerrainScene scene;
    VhCanvas canvas={fb,STRIDE,WIDTH,HEIGHT};
    size_t prims=98u,px=99u;
    setup();
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    /* Original insertion order: A then far C then same-depth B.
     * Actual PC chain order: C (far) then B then A (bucket LIFO). */
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(enqueue(&scene,&c,green_clut)==2);
    assert(enqueue(&scene,&b,blue_clut)==2);
    assert(scene.count==3u);
    assert(heads[832]==1u);
    assert(heads[896]==2u);
    assert(nodes[2].next==0u);
    assert(nodes[0].next==SIZE_MAX);
    assert(vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                  256,pack,NULL,&prims,&px));
    assert(prims==3u && px>512u);
    assert(observations==3u);
    assert(observed[0]==UINT32_C(0xff00ff00));
    assert(observed[1]==UINT32_C(0xff0000ff));
    assert(observed[2]==UINT32_C(0xffff0000));
    assert(fb[25*STRIDE+25]==UINT32_C(0xffff0000));
    assert(fb[19*STRIDE+25]==CLEAR);
    assert(fb[25*STRIDE+WIDTH]==CLEAR);
    assert(fb[(HEIGHT-1)*STRIDE+(STRIDE-1)]==CLEAR);
}

static void test_out_of_range_and_no_material_do_not_queue(void) {
    VhMap02OtTerrainScene scene;
    VhMap02TerrainQuad hidden;
    setup();
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    hidden=a;
    hidden.drawable=0;
    assert(vh_map02_ot_scene_add(&scene,&hidden,NULL,0,NULL,0,NULL,NULL)==1);
    assert(scene.count==0);
    hidden=a;
    hidden.projection.ot_slot=3;
    assert(enqueue(&scene,&hidden,red_clut)==0);
    hidden=a;
    hidden.projection.depth=1030;
    assert(enqueue(&scene,&hidden,red_clut)==0);
    assert(scene.count==0);
    assert(vh_map02_ot_scene_add(&scene,&a,NULL,0,red_clut,32,NULL,NULL)==0);
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(enqueue(&scene,&b,blue_clut)==2);
    assert(enqueue(&scene,&c,green_clut)==2);
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(enqueue(&scene,&a,red_clut)==0);
    assert(scene.count==MAXNODES);
}

static void test_preflight_rejects_corrupted_chain_without_writes(void) {
    VhMap02OtTerrainScene scene;
    VhCanvas canvas={fb,STRIDE,WIDTH,HEIGHT};
    size_t prims=77u,px=88u;
    setup();
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(enqueue(&scene,&b,blue_clut)==2);
    nodes[0].next=0; /* cycle in same bucket */
    assert(!vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                   256,pack,NULL,&prims,&px));
    assert(prims==77u && px==88u);
    assert(fb[25*STRIDE+25]==CLEAR);
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    assert(enqueue(&scene,&a,red_clut)==2);
    nodes[0].quad=&c; /* wrong slot for this depth */
    assert(!vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                   256,pack,NULL,&prims,&px));
    assert(prims==77u && px==88u);
    assert(fb[25*STRIDE+25]==CLEAR);
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(!vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                   255,pack,NULL,&prims,&px));
    assert(prims==77u && px==88u);
    assert(fb[25*STRIDE+25]==CLEAR);
    assert(!vh_map02_ot_scene_draw(&scene,NULL,scratch,classes,
                                   256,pack,NULL,&prims,&px));
    assert(prims==77u && px==88u);
}

static void test_reuse_and_empty_scene(void) {
    VhMap02OtTerrainScene scene;
    VhCanvas canvas={fb,STRIDE,WIDTH,HEIGHT};
    size_t prims=77u,px=88u;
    setup();
    assert(!vh_map02_ot_scene_init(NULL,heads,OT,nodes,MAXNODES));
    assert(!vh_map02_ot_scene_init(&scene,NULL,OT,nodes,MAXNODES));
    assert(!vh_map02_ot_scene_init(&scene,heads,4,nodes,MAXNODES));
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    assert(vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                  256,pack,NULL,&prims,&px));
    assert(prims==0u && px==0u && fb[25*STRIDE+25]==CLEAR);
    assert(enqueue(&scene,&a,red_clut)==2);
    assert(vh_map02_ot_scene_init(&scene,heads,OT,nodes,MAXNODES));
    assert(scene.count==0 && heads[896]==SIZE_MAX);
    prims=77u;px=88u;
    assert(vh_map02_ot_scene_draw(&scene,&canvas,scratch,classes,
                                  256,pack,NULL,&prims,&px));
    assert(prims==0u && px==0u && fb[25*STRIDE+25]==CLEAR);
}

int main(void) {
    test_depth_and_lifo_bucket_order();
    test_out_of_range_and_no_material_do_not_queue();
    test_preflight_rejects_corrupted_chain_without_writes();
    test_reuse_and_empty_scene();
    puts("MAP02 terrain OT compositor: sorted depth, per-slot AddPrim LIFO, and safe frame replay passed");
    return 0;
}
