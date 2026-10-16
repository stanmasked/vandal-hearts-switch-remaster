#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../source/map02_terrain_quad.h"

/* These fixtures are invented, NOT original MAP02 geometry or pixels. */
enum { WIDTH=56, HEIGHT=48, STRIDE=60, WORK=16*16 };
static uint8_t tile[VH_MAP02_FACE_RECORD_BYTES];
static uint8_t atlas[256*128];
static uint8_t clut[32];
static uint32_t fb[STRIDE*HEIGHT];
static uint32_t work_rgb[WORK];
static uint8_t work_class[WORK];
static unsigned blend_calls;
static const uint32_t BG = 0x11223344u;

static void put16(uint8_t *p, size_t at, int v) {
    uint16_t bits=(uint16_t)v;
    p[at]=(uint8_t)bits;
    p[at+1]=(uint8_t)(bits>>8);
}
static void vertex(unsigned idx, int x,int y,int z) {
    put16(tile,idx*8u,x);
    put16(tile,idx*8u+2u,y);
    put16(tile,idx*8u+4u,z);
}
static void setup_tile(void) {
    memset(tile,0,sizeof tile);
    put16(tile,176,241);
    tile[212]=0; tile[213]=1; tile[214]=2; tile[215]=3;
    tile[284]=7;
    tile[302]=1;
    vertex(0,0,0,512);
    vertex(1,32,0,512);
    vertex(2,32,32,512);
    vertex(3,0,32,512);
}
static VhMap02ProjectCamera camera(void) {
    VhMap02ProjectCamera c={0};
    c.rt[0][0]=c.rt[1][1]=c.rt[2][2]=4096;
    c.h=256;
    c.zsf4=256;
    c.ofx=20<<16;
    c.ofy=20<<16;
    return c;
}
static VhCanvas canvas(void) {
    VhCanvas c={fb,STRIDE,WIDTH,HEIGHT};
    return c;
}
static uint32_t pack(uint8_t r,uint8_t g,uint8_t b,void *unused) {
    (void)unused;
    return 0xff000000u | ((uint32_t)r<<16) | ((uint32_t)g<<8) | b;
}
static uint32_t blend(uint32_t dst,uint32_t src,void *unused) {
    (void)unused;
    ++blend_calls;
    return dst ^ src;
}
static void setup_atlas(void) {
    unsigned x,y;
    memset(atlas,0,sizeof atlas);
    memset(clut,0,sizeof clut);
    for (x=1;x<16;++x) {
        uint16_t color=(uint16_t)((x<<10u) | (x<<5u) | x);
        if (x==2) color|=0x8000u;
        put16(clut,2u*x,color);
    }
    for(y=192;y<208;++y)
        for(x=240;x<256;x+=2) {
            unsigned a=x-240u, b=a+1u;
            atlas[y*128u+x/2u]=(uint8_t)(a|(b<<4u));
        }
}
static void clear_pixels(void) {
    for(size_t i=0;i<STRIDE*HEIGHT;++i) fb[i]=BG;
    for(size_t i=0;i<WORK;++i) { work_rgb[i]=0; work_class[i]=0; }
    blend_calls=0;
}
static VhMap02TerrainQuad prepare(void) {
    VhMap02TerrainQuad q={0};
    VhMap02ProjectCamera c=camera();
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,
                                         1024,240,192,15,15,&q));
    return q;
}

static void test_exact_quad_projection_uv_and_raw_clut_pixels(void) {
    VhMap02TerrainQuad q;
    VhCanvas c=canvas();
    size_t written=999u;
    unsigned x,y;
    setup_tile();
    setup_atlas();
    clear_pixels();
    q=prepare();
    assert(q.material==241 && q.shade==7 && q.face==0);
    assert(q.drawable && q.projection.visible && q.projection.ot_in_bounds);
    assert(q.projection.nclip_mac0==256);
    assert(q.projection.otz==128 && q.projection.depth==128);
    assert(q.projection.ot_slot==896);
    assert(q.gpu_ft4[0].x==20 && q.gpu_ft4[0].y==20);
    assert(q.gpu_ft4[1].x==36 && q.gpu_ft4[1].y==20);
    assert(q.gpu_ft4[2].x==20 && q.gpu_ft4[2].y==36);
    assert(q.gpu_ft4[3].x==36 && q.gpu_ft4[3].y==36);
    assert(q.gpu_ft4[0].u==240 && q.gpu_ft4[0].v==192);
    assert(q.gpu_ft4[1].u==255 && q.gpu_ft4[1].v==192);
    assert(q.gpu_ft4[2].u==240 && q.gpu_ft4[2].v==207);
    assert(q.gpu_ft4[3].u==255 && q.gpu_ft4[3].v==207);
    assert(vh_map02_draw_terrain_4bpp(
        &c,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK,pack,NULL,blend,NULL,&written));
    assert(written == 15u*16u); /* exactly one transparent source column */
    assert(blend_calls == 16u);
    assert(fb[20*STRIDE+20] == BG); /* CLUT[0]==0 is transparent */
    assert(fb[20*STRIDE+21] == pack(8,8,8,NULL));
    assert(fb[20*STRIDE+22] == (BG ^ pack(16,16,16,NULL)));
    assert(fb[20*STRIDE+23] == pack(24,24,24,NULL));
    assert(fb[35*STRIDE+35] == pack(123,123,123,NULL));
    for(y=0;y<HEIGHT;++y)
        for(x=0;x<STRIDE;++x)
            if (x<20 || x>=36 || y<20 || y>=36 || x==20)
                assert(fb[y*STRIDE+x]==BG);
}

static void test_backface_and_invalid_ot_skip_pixel_writes(void) {
    VhMap02ProjectCamera c=camera();
    VhCanvas screen=canvas();
    VhMap02TerrainQuad q={0};
    size_t n=888;
    setup_tile();setup_atlas();clear_pixels();
    /* Original NCLIP sign flips if face[1],face[2] are reversed. */
    tile[213]=2;tile[214]=1;
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,
                                         1024,240,192,15,15,&q));
    assert(!q.drawable && !q.projection.visible);
    assert(vh_map02_draw_terrain_4bpp(
        &screen,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK,pack,NULL,blend,NULL,&n));
    assert(n==0 && fb[20*STRIDE+20]==BG && blend_calls==0);
    setup_tile();
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,
                                         64,240,192,15,15,&q));
    assert(!q.drawable && q.projection.visible && !q.projection.ot_in_bounds);
    n=7;
    assert(vh_map02_draw_terrain_4bpp(
        &screen,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK,pack,NULL,NULL,NULL,&n));
    assert(n==0);
}

static void test_null_gfx_skips_unusable_vertices_like_original(void) {
    VhMap02ProjectCamera c=camera();
    VhMap02TerrainQuad q={0};
    setup_tile();
    put16(tile,176,0);
    tile[212]=255;tile[213]=255;tile[214]=255;tile[215]=255;
    assert(vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,
                                         1024,240,192,15,15,&q));
    assert(q.material==0 && !q.drawable);
    assert(!q.projection.visible);
    assert(q.shade==7);
}

static void test_fail_closed_without_output_mutation(void) {
    VhMap02ProjectCamera c=camera();
    VhMap02TerrainQuad q={0}, marker;
    VhCanvas screen=canvas();
    size_t n=987;
    setup_tile();
    setup_atlas();
    clear_pixels();
    q.material=-123;
    q.face=17;
    marker=q;
    assert(!vh_map02_prepare_terrain_quad(tile,303,0,&c,1024,
                                          240,192,15,15,&q));
    assert(q.material==marker.material && q.face==marker.face);
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,18,&c,1024,
                                          240,192,15,15,&q));
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,1,&c,1024,
                                          240,192,15,15,&q));
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,1024,
                                          250,192,15,15,&q));
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,1024,
                                          240,192,0,15,&q));
    assert(!vh_map02_prepare_terrain_quad(NULL,sizeof tile,0,&c,1024,
                                          240,192,15,15,&q));
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,NULL,1024,
                                          240,192,15,15,&q));
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,1024,
                                          240,192,15,15,NULL));
    assert(q.material==marker.material && q.face==marker.face);
    tile[302]=19;
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,1024,
                                          240,192,15,15,&q));
    tile[302]=1;
    tile[212]=22;
    assert(!vh_map02_prepare_terrain_quad(tile,sizeof tile,0,&c,1024,
                                          240,192,15,15,&q));
    setup_tile();
    q=prepare();
    assert(!vh_map02_draw_terrain_4bpp(
        &screen,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK-1,pack,NULL,blend,NULL,&n));
    assert(n==987 && fb[20*STRIDE+21]==BG);
    assert(!vh_map02_draw_terrain_4bpp(
        &screen,&q,atlas,sizeof atlas,clut,31,
        work_rgb,work_class,WORK,pack,NULL,blend,NULL,&n));
    assert(n==987 && fb[20*STRIDE+21]==BG);
    assert(!vh_map02_draw_terrain_4bpp(
        &screen,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK,pack,NULL,blend,NULL,NULL));
    assert(n==987);
    assert(!vh_map02_draw_terrain_4bpp(
        NULL,&q,atlas,sizeof atlas,clut,sizeof clut,
        work_rgb,work_class,WORK,pack,NULL,blend,NULL,&n));
    assert(n==987);
}

static void test_two_source_faces_keep_material_uv_and_shared_projection(void) {
    VhMap02ProjectCamera cam=camera();
    VhMap02TerrainQuad left={0},right={0};
    VhMap02ProjectVertex corners[2][4] = {
        {{0,0,512},{100,0,640},{100,100,640},{0,100,512}},
        {{100,0,640},{200,0,640},{200,100,640},{100,100,640}}
    };
    const unsigned vertex_order[2][4]={{0,1,2,3},{1,4,5,2}};
    const VhMap02ProjectVertex all[6] = {
        {0,0,512},{100,0,640},{100,100,640},
        {0,100,512},{200,0,640},{200,100,640}
    };
    VhMap02ProjectFace expected[2]={{0}};
    VhMap02TerrainQuad *prepared[2]={&left,&right};
    setup_tile();
    tile[302]=2;
    put16(tile,176u,241);
    put16(tile,178u,497);
    tile[284]=7; tile[285]=19;
    for(unsigned i=0;i<6u;++i)
        vertex(i,all[i].x,all[i].y,all[i].z);
    for(unsigned f=0;f<2u;++f) {
        for(unsigned i=0;i<4u;++i)
            tile[212u+4u*f+i]=(uint8_t)vertex_order[f][i];
        assert(vh_map02_project_face(&cam,corners[f],1024,&expected[f]));
    }
    assert(vh_map02_prepare_terrain_quad(
        tile,sizeof tile,0,&cam,1024,0,0,15,15,&left));
    assert(vh_map02_prepare_terrain_quad(
        tile,sizeof tile,1,&cam,1024,16,32,15,15,&right));
    assert(left.drawable && right.drawable);
    assert(left.face==0 && right.face==1);
    assert(left.material==241 && right.material==497);
    assert(left.shade==7 && right.shade==19);
    assert(left.u==0 && left.v==0 && right.u==16 && right.v==32);
    assert(left.projection.otz != right.projection.otz);
    for(unsigned f=0;f<2u;++f) {
        const VhMap02TerrainQuad *q=prepared[f];
        assert(q->projection.otz==expected[f].otz);
        assert(q->projection.nclip_mac0==expected[f].nclip_mac0);
        assert(q->projection.ot_slot==expected[f].ot_slot);
        for(unsigned k=0;k<4u;++k) {
            assert(q->gpu_ft4[k].x==(float)expected[f].gpu[k].x);
            assert(q->gpu_ft4[k].y==(float)expected[f].gpu[k].y);
        }
    }
    assert(left.gpu_ft4[1].x==right.gpu_ft4[0].x);
    assert(left.gpu_ft4[1].y==right.gpu_ft4[0].y);
    assert(left.gpu_ft4[3].x==right.gpu_ft4[2].x);
    assert(left.gpu_ft4[3].y==right.gpu_ft4[2].y);
    /* Face 1 rejected when source faceCt is reduced; no stale result. */
    tile[302]=1;
    assert(!vh_map02_prepare_terrain_quad(
        tile,sizeof tile,1,&cam,1024,16,32,15,15,&right));
    assert(right.face==1 && right.material==497);
}

int main(void) {
    test_exact_quad_projection_uv_and_raw_clut_pixels();
    test_backface_and_invalid_ot_skip_pixel_writes();
    test_null_gfx_skips_unusable_vertices_like_original();
    test_fail_closed_without_output_mutation();
    test_two_source_faces_keep_material_uv_and_shared_projection();
    puts("MAP02 decoded tile -> GTE -> indexed CLUT4 -> FT4 RGBA32 tests passed");
    return 0;
}
