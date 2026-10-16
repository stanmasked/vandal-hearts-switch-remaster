/*
 * v58: synthetic PC-port OT GP0(E6) interleaving within ONE real DrawOTag.
 * Original pinned PC-port gpu.c/raster.c are built and executed after guarded
 * v57+v58 disposable-checkout patches. No game assets.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define X 64
#define Y 64
#define W 48
#define H 48
#define S 2
#define HW (W*S)
#define HH (H*S)
#define STRIDE (1024*S)
#define FILLERS 64
#define MAX_STEPS 4

typedef struct { unsigned command,texel; int semi; } Step;
typedef struct {
    const char *name;
    int bg,cx,cy,cw,ch,abr,n;
    Step step[MAX_STEPS];
} Case;
static const Case cases[]={
    {"mark_skip",0x0010,0,0,320,240,0,2,
        {{0xe6000001u,0x001f,0},{0xe6000002u,0x03e0,0}}},
    {"reopen",0x0010,0,0,320,240,0,4,
        {{0xe6000001u,0x001f,0},{0xe6000002u,0x03e0,0},
         {0xe6000000u,0x7c00,0},{0xe6000002u,0x03e0,0}}},
    {"abr0",0x0010,0,0,320,240,0,3,
        {{0xe6000001u,0x001f,0},{0xe6000000u,0x7c00,0},
         {0xe6000002u,0x83e0,1}}},
    {"abr1",0x0010,0,0,320,240,1,3,
        {{0xe6000001u,0x001f,0},{0xe6000000u,0x7c00,0},
         {0xe6000002u,0x83e0,1}}},
    {"abr2",0x0010,0,0,320,240,2,3,
        {{0xe6000001u,0x001f,0},{0xe6000000u,0x7c00,0},
         {0xe6000002u,0x83e0,1}}},
    {"abr3",0x0010,0,0,320,240,3,3,
        {{0xe6000001u,0x001f,0},{0xe6000000u,0x7c00,0},
         {0xe6000002u,0x83e0,1}}},
    {"zero_texel",0x0010,0,0,320,240,0,2,
        {{0xe6000001u,0x0000,1},{0xe6000002u,0x03e0,0}}},
    {"invalid_reserved",0x0010,0,0,320,240,0,2,
        {{0xe6000001u,0x001f,0},{0xe6000004u,0x03e0,0}}},
    {"clip_mask",0x0010,75,74,10,12,0,2,
        {{0xe6000001u,0x001f,0},{0xe6000003u,0x83e0,1}}}
};
#define NCASES ((int)(sizeof(cases)/sizeof(cases[0])))

typedef struct {
    DR_MODE mode;
    DR_MASK mask[MAX_STEPS];
    POLY_FT4 poly[MAX_STEPS];
    TILE filler[FILLERS];
    u32 ot[8];
} Packets;
static unsigned short (*vram)[1024];
static const unsigned short *hires;
static unsigned short observed[HW*HH];
void V58_BeginCase(const char *name);

static unsigned long long hash_native(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=Y;y<Y+H;y++)for(x=X;x<X+W;x++){h^=vram[y][x];h*=1099511628211ull;}
    return h;
}
static unsigned long long hash_hires(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=Y*S;y<(Y+H)*S;y++)for(x=X*S;x<(X+W)*S;x++){
        h^=hires[(size_t)y*STRIDE+x];h*=1099511628211ull;
    }
    return h;
}
static void clear_area(unsigned short bg) {
    int x,y;
    for(y=Y;y<Y+H;y++)for(x=X;x<X+W;x++)vram[y][x]=bg;
    HiresMirrorRect(X,Y,W,H);
}
static void build(Packets *p,const Case *c) {
    RECT tw;
    int i;
    memset(p,0,sizeof(*p));
    setRECT(&tw,0,0,256,256);
    SetDrawMode(&p->mode,0,0,GetTPage(2,c->abr,448,0),&tw);
    for(i=0;i<c->n;i++){
        PC_SetDrawMaskPacket(&p->mask[i],c->step[i].command);
        SetPolyFT4(&p->poly[i]);
        setRGB0(&p->poly[i],128,128,128);
        setXYWH(&p->poly[i],70,70,20,20);
        setUVWH(&p->poly[i],20+i,192,0,0);
        p->poly[i].tpage=GetTPage(2,c->abr,448,0);
        p->poly[i].clut=0;
        SetSemiTrans(&p->poly[i],c->step[i].semi);
    }
    for(i=0;i<FILLERS;i++){
        SetTile(&p->filler[i]);setRGB0(&p->filler[i],0,0,0);
        setXY0(&p->filler[i],250+i%8,204+i/8);setWH(&p->filler[i],1,1);
    }
    ClearOTag(p->ot,8);
    for(i=FILLERS-1;i>=0;i--)AddPrim(&p->ot[7],&p->filler[i]);
    for(i=c->n-1;i>=0;i--){
        AddPrim(&p->ot[0],&p->poly[i]);
        AddPrim(&p->ot[0],&p->mask[i]);
    }
    AddPrim(&p->ot[0],&p->mode);
}
static void quad_points(const POLY_FT4 *q,RVert *a,RVert *b,RVert *c,RVert *d){
    a->x=q->x0;a->y=q->y0;a->u=q->u0;a->v=q->v0;
    b->x=q->x1;b->y=q->y1;b->u=q->u1;b->v=q->v1;
    c->x=q->x2;c->y=q->y2;c->u=q->u2;c->v=q->v2;
    d->x=q->x3;d->y=q->y3;d->u=q->u3;d->v=q->v3;
}
static int run_one(const Case *c,int workers) {
    Packets p;
    DRAWENV env;DISPENV disp;
    RenderCtx rc;
    RVert a,b,d,e;
    unsigned long long n_hash,h_hash,d_hash;
    unsigned short pn,ph,outn,outh;
    int i,x,y,mask_set=0,mask_check=0;
    build(&p,c);
    clear_area((unsigned short)c->bg);
    for(i=0;i<c->n;i++)vram[192][468+i]=(unsigned short)c->step[i].texel;
    SetDefDrawEnv(&env,0,0,320,240);
    env.clip.x=c->cx;env.clip.y=c->cy;env.clip.w=c->cw;env.clip.h=c->ch;
    env.dtd=0;
    PutDrawEnv(&env);
    SetDefDispEnv(&disp,0,0,320,240);PutDispEnv(&disp);
    /* Set a known initial mask state. All subsequent transitions are
     * consumed as REAL OT mask packets inside the same DrawOTag. */
    if(!PC_GpuGp0MaskE6(0xe6000000u))return 0;
    V58_BeginCase(c->name);
    DrawOTag(p.ot);
    n_hash=hash_native();h_hash=hash_hires();
    pn=vram[80][80];ph=hires[(size_t)161*STRIDE+161];
    outn=vram[66][66];outh=hires[(size_t)133*STRIDE+133];
    for(y=0;y<HH;y++)for(x=0;x<HW;x++)
        observed[y*HW+x]=hires[(size_t)(Y*S+y)*STRIDE+X*S+x];

    /* Exact direct-vs-deferred full-frame HD comparison on original C path.
     * Each mask state's value comes from its in-OT GP0 command, in order. */
    clear_area((unsigned short)c->bg);
    memset(&rc,0,sizeof(rc));
    rc.clipX=c->cx;rc.clipY=c->cy;rc.clipW=c->cw;rc.clipH=c->ch;
    rc.target=1;rc.scale=S;
    for(i=0;i<c->n;i++){
        unsigned command=c->step[i].command;
        if((command&~3u)==0xe6000000u){
            mask_set=command&1u;
            mask_check=(command>>1)&1u;
        }
        rc.maskSet=mask_set;rc.maskCheck=mask_check;
        quad_points(&p.poly[i],&a,&b,&d,&e);
        FillQuad(&rc,a,b,d,e,128,128,128,1,
                 p.poly[i].tpage,0,c->step[i].semi,c->abr);
    }
    d_hash=hash_hires();
    for(y=0;y<HH;y++)for(x=0;x<HW;x++){
        unsigned short now=hires[(size_t)(Y*S+y)*STRIDE+X*S+x];
        if(now!=observed[y*HW+x]){
            fprintf(stderr,"V58 FAIL direct/deferred name=%s threads=%d x=%d y=%d deferred=%u direct=%u\n",
                c->name,workers,x,y,(unsigned)observed[y*HW+x],(unsigned)now);
            return 0;
        }
    }
    printf("V58CASE name=%s workers=%d n=%d background=%d clipx=%d clipy=%d clipw=%d cliph=%d abr=%d "
           "nativehash=%016llx hihash=%016llx directhash=%016llx native_probe=%u hires_probe=%u "
           "outside_native=%u outside_hires=%u pixels=%d\n",
        c->name,workers,c->n,c->bg,c->cx,c->cy,c->cw,c->ch,c->abr,
        n_hash,h_hash,d_hash,(unsigned)pn,(unsigned)ph,
        (unsigned)outn,(unsigned)outh,HW*HH);
    return h_hash==d_hash;
}
int main(void) {
    int workers=getenv("VH_RASTER_THREADS")?atoi(getenv("VH_RASTER_THREADS")):0;
    size_t nbytes=0;
    int i;
    if(workers!=1&&workers!=2&&workers!=4)return 2;
    if(setenv("VH_INTERNAL_SCALE","2",1)!=0||
       setenv("VH_ACCURATE","1",1)!=0)return 2;
    HiresEnsure();
    vram=PC_GpuVram();
    hires=(const unsigned short *)PC_GpuHiresBytes(&nbytes);
    if(!vram||!hires||PC_GpuGetInternalScale()!=2||nbytes<2048u*1024u*2u)return 2;
    for(i=0;i<NCASES;i++)if(!run_one(&cases[i],workers))return 3;
    fprintf(stderr,"V58 REAL_OT_MASK_INTERLEAVE=%d THREADS=%d SYNTHETIC_ONLY\n",NCASES,workers);
    return 0;
}
