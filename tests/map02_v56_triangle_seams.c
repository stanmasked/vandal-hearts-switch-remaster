/*
 * v56: real pinned PC-port original ClearOTag/AddPrim/DrawOTag ->
 * POLY_FT4 -> two ORIGINAL DDA triangles, 2x deferred threads.
 *
 * Strictly SYNTHETIC, never a retail game frame. The masked destination
 * case is a REGRESSION CHARACTERIZATION: current PC PutPixel lacks the PS1
 * GP0(E6) destination mask-test, so it MUST NOT be advertised as PS1 parity.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define RX 64
#define RY 64
#define RW 48
#define RH 48
#define SC 2
#define HRW (RW*SC)
#define HRH (RH*SC)
#define HSTRIDE 2048
#define CASES 9
#define FILLERS 64

typedef struct {
    const char *name;
    int texel,background,semi,abr;
    int minx,miny,maxx,maxy;
    int clipx,clipy,clipw,cliph;
    int skew;
} Case;
static const Case specs[CASES]={
    {"stp_abr0",0x801f,0x4210,1,0,70,70,90,90,0,0,320,240,0},
    {"stp_abr1",0x83e0,0x2529,1,1,70,70,90,90,0,0,320,240,0},
    {"stp_abr2",0xfc00,0x5ad6,1,2,70,70,90,90,0,0,320,240,0},
    {"stp_abr3",0x801f,0x18c6,1,3,70,70,90,90,0,0,320,240,0},
    {"nonstp_opaque",0x001f,0x4210,1,1,70,70,90,90,0,0,320,240,0},
    {"transparent_zero",0x0000,0x369c,1,0,70,70,90,90,0,0,320,240,0},
    {"clipped_edges",0x83e0,0x4210,1,1,70,70,90,90,75,74,10,12,0},
    {"destination_bit15",0x03e0,0x8010,0,0,70,70,90,90,0,0,320,240,0},
    {"skewed_quad",0x801f,0x4210,1,0,70,70,90,90,0,0,320,240,1}
};
typedef struct {
    DR_MODE mode;
    POLY_FT4 quad;
    TILE fillers[FILLERS];
    u32 ot[8];
} Packets;
static unsigned short (*vram)[1024];
static const unsigned short *hd;
static unsigned short saved[HRW*HRH];

static unsigned long long hash_native(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=RY;y<RY+RH;y++)for(x=RX;x<RX+RW;x++){
        h ^= vram[y][x];h*=1099511628211ull;
    }
    return h;
}
static unsigned long long hash_hires(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=RY*SC;y<(RY+RH)*SC;y++)for(x=RX*SC;x<(RX+RW)*SC;x++){
        h ^= hd[(size_t)y*HSTRIDE+x];h*=1099511628211ull;
    }
    return h;
}
static void reset_area(unsigned short background) {
    int x,y;
    for(y=RY;y<RY+RH;y++)for(x=RX;x<RX+RW;x++) vram[y][x]=background;
    HiresMirrorRect(RX,RY,RW,RH);
}
static void positions(POLY_FT4 *q,const Case *c) {
    q->x0=c->minx;q->y0=c->miny;
    q->x1=c->maxx;q->y1=c->miny;
    q->x2=c->minx;q->y2=c->maxy;
    q->x3=c->maxx;q->y3=c->maxy;
    if(c->skew){
        q->x1+=1;q->y1+=4;q->x2-=2;q->x3-=1;q->y3+=4;
    }
}
static void points(const POLY_FT4 *q,RVert *a,RVert *b,RVert *c,RVert *d) {
    a->x=q->x0;a->y=q->y0;a->u=q->u0;a->v=q->v0;
    b->x=q->x1;b->y=q->y1;b->u=q->u1;b->v=q->v1;
    c->x=q->x2;c->y=q->y2;c->u=q->u2;c->v=q->v2;
    d->x=q->x3;d->y=q->y3;d->u=q->u3;d->v=q->v3;
}
static void setup(Packets *p,const Case *c) {
    RECT win;
    int i;
    memset(p,0,sizeof(*p));
    setRECT(&win,0,0,256,256);
    SetDrawMode(&p->mode,0,0,GetTPage(2,c->abr,448,0),&win);
    SetPolyFT4(&p->quad);
    setRGB0(&p->quad,128,128,128);
    positions(&p->quad,c);
    setUVWH(&p->quad,20,192,0,0);
    p->quad.tpage=GetTPage(2,c->abr,448,0);
    p->quad.clut=0;
    SetSemiTrans(&p->quad,c->semi);
    for(i=0;i<FILLERS;i++) {
        SetTile(&p->fillers[i]);setRGB0(&p->fillers[i],0,0,0);
        setXY0(&p->fillers[i],250+i%8,204+i/8);
        setWH(&p->fillers[i],1,1);
    }
    ClearOTag(p->ot,8);
    for(i=FILLERS-1;i>=0;i--)AddPrim(&p->ot[7],&p->fillers[i]);
    AddPrim(&p->ot[0],&p->quad);
    AddPrim(&p->ot[0],&p->mode);
}
static int run_case(const Case *c,int threads) {
    Packets p;
    DRAWENV env;DISPENV disp;
    RVert a,b,d,e;
    RenderCtx rc;
    unsigned long long nh,hh,mh;
    unsigned short nprobe,hprobe,spare_n,spare_hd;
    int x,y;
    setup(&p,c);
    vram[192][468]=(unsigned short)c->texel;
    reset_area((unsigned short)c->background);
    SetDefDrawEnv(&env,0,0,320,240);
    env.clip.x=c->clipx;env.clip.y=c->clipy;
    env.clip.w=c->clipw;env.clip.h=c->cliph;
    env.dtd=0;
    PutDrawEnv(&env);
    SetDefDispEnv(&disp,0,0,320,240);
    PutDispEnv(&disp);
    DrawOTag(p.ot);
    nh=hash_native();hh=hash_hires();
    nprobe=vram[80][80];
    hprobe=hd[(size_t)161*HSTRIDE+161];
    spare_n=vram[66][66];
    spare_hd=hd[(size_t)133*HSTRIDE+133];
    for(y=0;y<HRH;y++)for(x=0;x<HRW;x++)
        saved[y*HRW+x]=hd[(size_t)(RY*SC+y)*HSTRIDE+RX*SC+x];

    /* Independent original-C direct GPU path on the SAME 2x scratch
     * framebuffer with identical synthetic source and screen clip. */
    reset_area((unsigned short)c->background);
    memset(&rc,0,sizeof(rc));
    rc.clipX=c->clipx;rc.clipY=c->clipy;
    rc.clipW=c->clipw;rc.clipH=c->cliph;
    rc.target=1;rc.scale=SC;
    points(&p.quad,&a,&b,&d,&e);
    FillQuad(&rc,a,b,d,e,128,128,128,1,
             p.quad.tpage,p.quad.clut,c->semi,c->abr);
    mh=hash_hires();
    for(y=0;y<HRH;y++)for(x=0;x<HRW;x++){
        unsigned short observed=hd[(size_t)(RY*SC+y)*HSTRIDE+RX*SC+x];
        if(observed!=saved[y*HRW+x]){
            fprintf(stderr,"V56 FAIL actual DrawOTag vs direct exact pixel case=%s workers=%d x=%d y=%d original=%u direct=%u\n",
              c->name,threads,x,y,(unsigned)saved[y*HRW+x],(unsigned)observed);
            return 0;
        }
    }
    printf("V56CASE name=%s workers=%d shape=%d abr=%d semi=%d texel=%d background=%d "
           "minx=%d miny=%d maxx=%d maxy=%d clipx=%d clipy=%d clipw=%d cliph=%d "
           "nativehash=%016llx hihash=%016llx directhash=%016llx "
           "native_probe=%u hires_probe=%u outside_native=%u outside_hires=%u "
           "pixels=%d\n",
           c->name,threads,c->skew,c->abr,c->semi,c->texel,c->background,
           c->minx,c->miny,c->maxx,c->maxy,c->clipx,c->clipy,c->clipw,c->cliph,
           nh,hh,mh,(unsigned)nprobe,(unsigned)hprobe,
           (unsigned)spare_n,(unsigned)spare_hd,HRW*HRH);
    return mh==hh;
}
int main(void) {
    int workers=getenv("VH_RASTER_THREADS")?atoi(getenv("VH_RASTER_THREADS")):0;
    size_t size=0;
    int i;
    if(workers!=1&&workers!=2&&workers!=4)return 2;
    if(setenv("VH_INTERNAL_SCALE","2",1)!=0||
       setenv("VH_ACCURATE","1",1)!=0) return 2;
    HiresEnsure();
    vram=PC_GpuVram();
    hd=(const unsigned short *)PC_GpuHiresBytes(&size);
    if(!vram||!hd||PC_GpuGetInternalScale()!=2||size<2048u*1024u*2) return 2;
    for(i=0;i<CASES;i++)if(!run_case(&specs[i],workers))return 3;
    fprintf(stderr,"V56 ORIGINAL_DDA_TRIANGLE_SEAMS=9 THREADS=%d SYNTHETIC_ONLY DEST_MASK_UNSUPPORTED\n",workers);
    return 0;
}
