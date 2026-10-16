/*
 * v57 executed original PC-port DrawOTag -> FillQuad -> DDA -> PutPixel.
 * All geometry, VRAM and OT packets are synthetic. Test real GP0(E6) mask
 * payload application before drawing and its state snapshot in deferred 2x.
 * 64 extra primitives force the multi-worker code path when configured.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define RX 64
#define RY 64
#define RW 48
#define RH 48
#define SCALE 2
#define HDW (RW*SCALE)
#define HDH (RH*SCALE)
#define STRIDE (1024*SCALE)
#define FILLERS 64

typedef struct {
    const char *name;
    int raw,bg,set,check,semi,abr,cx,cy,cw,ch,two;
} Case;
static const Case cases[] = {
    {"default_overwrite", 0x03e0,0x8010,0,0,0,0,0,0,320,240,0},
    {"masked_preserved",  0x03e0,0x8010,0,1,0,0,0,0,320,240,0},
    {"unmasked_allowed",  0x03e0,0x0010,0,1,0,0,0,0,320,240,0},
    {"force_opaque",     0x03e0,0x0010,1,0,0,0,0,0,320,240,0},
    {"force_and_check",  0x03e0,0x0010,1,1,0,0,0,0,320,240,0},
    {"masked_force_skip",0x03e0,0x8010,1,1,0,0,0,0,320,240,0},
    {"zero_texel_force", 0x0000,0x0010,1,0,1,0,0,0,320,240,0},
    {"masked_stp_skip",  0x801f,0x9210,0,1,1,0,0,0,320,240,0},
    {"stp_abr0",         0x801f,0x4210,1,0,1,0,0,0,320,240,0},
    {"stp_abr1",         0x83e0,0x2529,1,0,1,1,0,0,320,240,0},
    {"stp_abr2",         0xfc00,0x5ad6,1,0,1,2,0,0,320,240,0},
    {"stp_abr3",         0x801f,0x18c6,1,0,1,3,0,0,320,240,0},
    {"nonstp_opaque",    0x001f,0x4210,1,0,1,1,0,0,320,240,0},
    {"mask_clip",        0x83e0,0x0010,1,1,1,1,75,74,10,12,0},
    /* Initial E6(1) writes 0x801f, then E6(2) refuses a green overdraw
       on the already marked destination. Two real DrawOTag submissions. */
    {"mask_transition",  0x001f,0x0010,1,0,0,0,0,0,320,240,1}
};
#define CASE_COUNT ((int)(sizeof(cases)/sizeof(cases[0])))

typedef struct {
    DR_MODE mode;
    POLY_FT4 q;
    TILE filler[FILLERS];
    u32 ot[8];
} Scene;

static unsigned short (*vram)[1024];
static const unsigned short *hires;
static unsigned short saved[HDW*HDH];

static unsigned long long native_hash(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=RY;y<RY+RH;y++)for(x=RX;x<RX+RW;x++){
        h^=vram[y][x];h*=1099511628211ull;
    }
    return h;
}
static unsigned long long hd_hash(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=RY*SCALE;y<(RY+RH)*SCALE;y++)
        for(x=RX*SCALE;x<(RX+RW)*SCALE;x++){
            h^=hires[(size_t)y*STRIDE+x];h*=1099511628211ull;
        }
    return h;
}
static void clear_test_rect(unsigned short color) {
    int x,y;
    for(y=RY;y<RY+RH;y++)for(x=RX;x<RX+RW;x++)vram[y][x]=color;
    HiresMirrorRect(RX,RY,RW,RH);
}
static void make_scene(Scene *s,const Case *c){
    RECT tw;
    int i;
    memset(s,0,sizeof(*s));
    setRECT(&tw,0,0,256,256);
    SetDrawMode(&s->mode,0,0,GetTPage(2,c->abr,448,0),&tw);
    SetPolyFT4(&s->q);
    setRGB0(&s->q,128,128,128);
    s->q.x0=70;s->q.y0=70;s->q.x1=90;s->q.y1=70;
    s->q.x2=70;s->q.y2=90;s->q.x3=90;s->q.y3=90;
    setUVWH(&s->q,20,192,0,0);
    s->q.tpage=GetTPage(2,c->abr,448,0);
    s->q.clut=0;
    SetSemiTrans(&s->q,c->semi);
    for(i=0;i<FILLERS;i++){
        SetTile(&s->filler[i]);setRGB0(&s->filler[i],0,0,0);
        setXY0(&s->filler[i],250+i%8,204+i/8);
        setWH(&s->filler[i],1,1);
    }
    ClearOTag(s->ot,8);
    for(i=FILLERS-1;i>=0;i--)AddPrim(&s->ot[7],&s->filler[i]);
    AddPrim(&s->ot[0],&s->q);
    AddPrim(&s->ot[0],&s->mode);
}
static void direct_ft4(const Scene *p,const Case *c,int set,int check) {
    RenderCtx rc;
    RVert a,b,d,e;
    memset(&rc,0,sizeof(rc));
    rc.clipX=c->cx;rc.clipY=c->cy;rc.clipW=c->cw;rc.clipH=c->ch;
    rc.target=1;rc.scale=SCALE;
    rc.maskSet=set;rc.maskCheck=check;
    a.x=p->q.x0;a.y=p->q.y0;a.u=p->q.u0;a.v=p->q.v0;
    b.x=p->q.x1;b.y=p->q.y1;b.u=p->q.u1;b.v=p->q.v1;
    d.x=p->q.x2;d.y=p->q.y2;d.u=p->q.u2;d.v=p->q.v2;
    e.x=p->q.x3;e.y=p->q.y3;e.u=p->q.u3;e.v=p->q.v3;
    FillQuad(&rc,a,b,d,e,128,128,128,1,p->q.tpage,0,c->semi,c->abr);
}
static int run_case(const Case *c,int workers) {
    Scene s;
    DRAWENV env;DISPENV disp;
    unsigned long long nh,hh,directh;
    unsigned short nativepx,hdpx,outer,outerhd;
    int x,y;
    make_scene(&s,c);
    clear_test_rect((unsigned short)c->bg);
    vram[192][468]=(unsigned short)c->raw;
    SetDefDrawEnv(&env,0,0,320,240);
    env.clip.x=c->cx;env.clip.y=c->cy;env.clip.w=c->cw;env.clip.h=c->ch;
    env.dtd=0;
    PutDrawEnv(&env);
    SetDefDispEnv(&disp,0,0,320,240);
    PutDispEnv(&disp);
    /* Verify invalid GP0 words and E6 reserved bits do NOT change state. */
    if(!PC_GpuGp0MaskE6(0xe6000000u+(unsigned)c->set+2u*(unsigned)c->check))
        return 0;
    if(PC_GpuGp0MaskE6(0xe6000004u)||PC_GpuGp0MaskE6(0xe5000000u))
        return 0;
    DrawOTag(s.ot);
    if(c->two){
        /* GP0(E6) persists between DrawOTag executions, and the same
         * HD framebuffer must retain the first pass's bit15 mask. */
        vram[192][468]=0x03e0;
        if(!PC_GpuGp0MaskE6(0xe6000002u))return 0;
        DrawOTag(s.ot);
    }
    nh=native_hash();hh=hd_hash();
    nativepx=vram[80][80];hdpx=hires[(size_t)161*STRIDE+161];
    outer=vram[66][66];outerhd=hires[(size_t)133*STRIDE+133];
    for(y=0;y<HDH;y++)for(x=0;x<HDW;x++)
        saved[y*HDW+x]=hires[(size_t)(RY*SCALE+y)*STRIDE+RX*SCALE+x];

    clear_test_rect((unsigned short)c->bg);
    vram[192][468]=(unsigned short)c->raw;
    direct_ft4(&s,c,c->set,c->check);
    if(c->two){
        vram[192][468]=0x03e0;
        direct_ft4(&s,c,0,1);
    }
    directh=hd_hash();
    for(y=0;y<HDH;y++)for(x=0;x<HDW;x++){
        unsigned short actual=hires[(size_t)(RY*SCALE+y)*STRIDE+RX*SCALE+x];
        if(actual!=saved[y*HDW+x]){
            fprintf(stderr,"V57 ERROR deferred/direct case=%s threads=%d x=%d y=%d expected=%u actual=%u\n",
                c->name,workers,x,y,(unsigned)saved[y*HDW+x],(unsigned)actual);
            return 0;
        }
    }
    printf("V57CASE name=%s workers=%d texel=%d background=%d maskset=%d maskcheck=%d "
           "semi=%d abr=%d clipx=%d clipy=%d clipw=%d cliph=%d two=%d "
           "nativehash=%016llx hihash=%016llx directhash=%016llx "
           "native_probe=%u hires_probe=%u outside_native=%u outside_hires=%u pixels=%d\n",
        c->name,workers,c->raw,c->bg,c->set,c->check,c->semi,c->abr,
        c->cx,c->cy,c->cw,c->ch,c->two,nh,hh,directh,
        (unsigned)nativepx,(unsigned)hdpx,(unsigned)outer,(unsigned)outerhd,HDW*HDH);
    return directh==hh;
}
int main(void){
    int workers=getenv("VH_RASTER_THREADS")?atoi(getenv("VH_RASTER_THREADS")):0;
    size_t size=0;
    int i;
    if(workers!=1&&workers!=2&&workers!=4)return 2;
    if(setenv("VH_INTERNAL_SCALE","2",1)!=0||
       setenv("VH_ACCURATE","1",1)!=0)return 2;
    HiresEnsure();
    vram=PC_GpuVram();
    hires=(const unsigned short *)PC_GpuHiresBytes(&size);
    if(!vram||!hires||PC_GpuGetInternalScale()!=2||
       size<2048u*1024u*2u)return 2;
    for(i=0;i<CASE_COUNT;i++)if(!run_case(&cases[i],workers))return 3;
    fprintf(stderr,"V57 EXECUTED_GP0_E6_SYNTHETIC=%d THREADS=%d NO_RETAIL_ASSETS\n",CASE_COUNT,workers);
    return 0;
}
