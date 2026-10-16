/*
 * v52: ORIGINAL public PC-port GPU, overlapping textured quads with distinct
 * semi-transparency, ABR, texture formats and GPU texture-window state.
 * All vertices, texture bytes, CLUT, and background are synthetic. Nothing
 * here is retail M_MAP02.PRS or a user asset. The source GPU is UNMODIFIED.
 *
 * The display list has 64 distant TILE fillers to force the original
 * two/four-worker band scheduler; their pixels cannot overlap the test quad.
 * For each scenario compare the entire 32x32 output direct vs deferred HD,
 * not only the probe pixel. Independent Python checks the actual layer order.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define MAX_LAYERS 5
#define N_SCENES 5
#define SX 80
#define SY 40
#define SW 16
#define SH 160
#define HS 2
#define PX 88
#define PY 88
#define HPX (2*PX+1)
#define HPY (2*PY)

typedef struct {
    int depth,raw,semi,abr,dither,maskx,masky,offx,offy,uvx,uvy;
} Layer;
typedef struct {
    const char *name;
    int count,reverse;
    unsigned short background;
    Layer layers[MAX_LAYERS];
} Scene;
#define L(dp,raw,semi,abr,dither,mx,my,ox,oy,u,v) \
    {dp,raw,semi,abr,dither,mx,my,ox,oy,u,v}
static const Scene SCENES[N_SCENES] = {
  {"mixed_stp",5,0,0x4210,{
    L(0,0x001f,0,0,0,0,0,0,0,208,192),
    L(1,0x83e0,1,0,0,0,0,0,0,210,192),
    L(2,0xfc00,1,1,0,0,0,0,0,210,192),
    L(0,0x0000,1,2,0,0,0,0,0,220,192),
    L(2,0x801f,1,2,0,0,0,0,0,212,192)
  }},
  {"mixed_reversed",5,1,0x4210,{
    L(0,0x001f,0,0,0,0,0,0,0,208,192),
    L(1,0x83e0,1,0,0,0,0,0,0,210,192),
    L(2,0xfc00,1,1,0,0,0,0,0,210,192),
    L(0,0x0000,1,2,0,0,0,0,0,220,192),
    L(2,0x801f,1,2,0,0,0,0,0,212,192)
  }},
  {"abr_chain",5,0,0x294a,{
    L(2,0x7c00,0,0,0,0,0,0,0,208,192),
    L(0,0x801f,1,0,0,0,0,0,0,212,192),
    L(1,0x83e0,1,1,0,0,0,0,0,212,192),
    L(2,0xfc00,1,2,0,0,0,0,0,211,192),
    L(0,0x8210,1,3,0,0,0,0,0,224,192)
  }},
  {"window_interleave",5,0,0x3ad5,{
    L(0,0x4210,0,0,0,1,1,0,0,216,200),
    L(1,0x0000,1,1,0,0,0,0,0,210,192),
    L(2,0x83e0,1,0,0,1,1,1,1,210,192),
    L(0,0x801f,1,3,0,0,0,0,0,220,192),
    L(1,0x7c00,1,2,0,0,0,0,0,216,192)
  }},
  {"dither_overdraw",5,0,0x1ce7,{
    L(0,0x4210,0,0,1,0,0,0,0,208,192),
    L(1,0x83e0,1,0,1,0,0,0,0,210,192),
    L(2,0x801f,1,3,1,0,0,0,0,210,192),
    L(1,0x0000,1,1,1,0,0,0,0,214,192),
    L(0,0xfc00,1,2,1,0,0,0,0,224,192)
  }}
};

static unsigned short (*s_vram)[1024];
static const unsigned short *s_hires;
static unsigned short hd_pixels[SW*HS*SH*HS];
static const int BAND_Y[]={55,60,119,120,179,180,190};
#define BAND_COUNT (sizeof(BAND_Y)/sizeof(BAND_Y[0]))

static const int HSSTRIDE=1024*HS;

static void quad(RVert *a,RVert *b,RVert *c,RVert *d,int u,int v) {
    a->x=SX; a->y=SY; a->u=u; a->v=v;
    b->x=SX+SW; b->y=SY; b->u=u; b->v=v;
    c->x=SX; c->y=SY+SH; c->u=u; c->v=v;
    d->x=SX+SW; d->y=SY+SH; d->u=u; d->v=v;
}
static void reset_region(unsigned short bg) {
    int x,y;
    for(y=SY;y<SY+SH;y++)
      for(x=SX;x<SX+SW;x++) s_vram[y][x]=bg;
    HiresMirrorRect(SX,SY,SW,SH);
}
static unsigned long long hash_region(void) {
    unsigned long long h=1469598103934665603ull;
    int x,y;
    for(y=SY*HS;y<(SY+SH)*HS;y++)
      for(x=SX*HS;x<(SX+SW)*HS;x++) {
        h^=s_hires[(size_t)y*HSSTRIDE+x];
        h*=1099511628211ull;
      }
    return h;
}
static int src_position(const Layer *p,int layeridx,int *tp,int *tx,int *ty,int *word,int *idx,
                        int *palx,int *paly,int *palette) {
    const int u=(p->uvx & ~(p->maskx*8))|((p->offx&p->maskx)*8);
    const int v=(p->uvy & ~(p->masky*8))|((p->offy&p->masky)*8);
    const int ppw=p->depth==0?4:(p->depth==1?2:1);
    const int clut=31978,baseX=(clut&63)*16,baseY=(clut>>6)&511;
    *tp=5+(p->depth<<7);
    *tx=(*tp&15)*64+u/ppw;
    *ty=((*tp>>4)&1)*256+v;
    *idx=p->depth==2?-1:p->depth==0?layeridx+1:32+layeridx;
    *palx=*idx<0?-1:baseX+*idx;
    *paly=*idx<0?-1:baseY;
    *palette=*idx<0?0:p->raw;
    *word=p->depth==0?(*idx)*0x1111:
          p->depth==1?(*idx)*0x0101:p->raw;
    return *tx>=0&&*tx<1024&&*ty>=0&&*ty<512&&
           (*palx<0||(*palx>=0&&*palx<1024&&*paly>=0&&*paly<512));
}
static void layer_ctx(RenderCtx *rc,const Layer *p,int target) {
    memset(rc,0,sizeof(*rc));
    rc->clipX=0; rc->clipY=0; rc->clipW=320; rc->clipH=240;
    rc->target=target; rc->scale=target?HS:1;
    rc->dither=p->dither;
    rc->twMaskX=p->maskx; rc->twMaskY=p->masky;
    rc->twOffX=p->offx; rc->twOffY=p->offy;
}
static void setup_textures(const Scene *s) {
    int i,usedX[MAX_LAYERS],usedY[MAX_LAYERS],nused=0;
    for(i=0;i<s->count;i++) {
       const Layer *p=&s->layers[i];
       int tp,tx,ty,word,idx,px,py,pal,j;
       if(!src_position(p,i,&tp,&tx,&ty,&word,&idx,&px,&py,&pal)){
          fprintf(stderr,"V52 FAIL unsafe texture source for %s layer%d\n",s->name,i);
          exit(3);
       }
       for(j=0;j<nused;j++) if(usedX[j]==tx&&usedY[j]==ty) {
          fprintf(stderr,"V52 FAIL texture word aliases another source %s layer%d\n",s->name,i);
          exit(3);
       }
       usedX[nused]=tx;usedY[nused++]=ty;
       s_vram[ty][tx]=(unsigned short)word;
       if(idx>=0)s_vram[py][px]=(unsigned short)pal;
    }
}
static void emit_layer(const Scene *s,int slot,int sourceIdx) {
    const Layer *p=&s->layers[sourceIdx];
    int tp,tx,ty,word,idx,px,py,pal;
    (void)src_position(p,sourceIdx,&tp,&tx,&ty,&word,&idx,&px,&py,&pal);
    printf("V52L scene=%s seq=%d source=%d depth=%d tpage=%d clut=31978 "
           "u=%d v=%d maskx=%d masky=%d offx=%d offy=%d tx=%d ty=%d "
           "word=%d index=%d palx=%d paly=%d palette=%d raw=%d semi=%d abr=%d dither=%d\n",
           s->name,slot,sourceIdx,p->depth,tp,p->uvx,p->uvy,
           p->maskx,p->masky,p->offx,p->offy,tx,ty,word,idx,px,py,pal,
           p->raw,p->semi,p->abr,p->dither);
}
static int run_scene(const Scene *s,int workers) {
    RVert a,b,c,d;
    RenderCtx rc;
    unsigned short native,direct,threaded;
    unsigned long long hash_direct,hash_threaded;
    int i,x,y;
    unsigned f;
    unsigned short band_native[BAND_COUNT],band_direct[BAND_COUNT],band_worker[BAND_COUNT];

    /* VRAM texture sources live far away from the output region. */
    setup_textures(s);
    reset_region(s->background);
    for(i=0;i<s->count;i++) {
        const int idx=s->reverse?s->count-1-i:i;
        const Layer *p=&s->layers[idx];
        const int tp=5+(p->depth<<7);
        layer_ctx(&rc,p,0);
        quad(&a,&b,&c,&d,p->uvx,p->uvy);
        FillQuad(&rc,a,b,c,d,128,128,128,1,tp,31978,p->semi,p->abr);
        emit_layer(s,i,idx);
    }
    native=s_vram[PY][PX];
    for(i=0;i<(int)BAND_COUNT;i++) band_native[i]=s_vram[BAND_Y[i]][PX];
    reset_region(s->background);
    for(i=0;i<s->count;i++) {
        const int idx=s->reverse?s->count-1-i:i;
        const Layer *p=&s->layers[idx];
        const int tp=5+(p->depth<<7);
        layer_ctx(&rc,p,1);
        quad(&a,&b,&c,&d,p->uvx,p->uvy);
        FillQuad(&rc,a,b,c,d,128,128,128,1,tp,31978,p->semi,p->abr);
    }
    direct=s_hires[(size_t)HPY*HSSTRIDE+HPX];
    hash_direct=hash_region();
    for(i=0;i<(int)BAND_COUNT;i++)
        band_direct[i]=s_hires[(size_t)(BAND_Y[i]*HS)*HSSTRIDE+HPX];
    for(y=0;y<SH*HS;y++)for(x=0;x<SW*HS;x++)
        hd_pixels[y*SW*HS+x]=s_hires[(size_t)(SY*HS+y)*HSSTRIDE+SX*HS+x];
    reset_region(s->background);
    HiresFrameReset();
    for(i=0;i<s->count;i++) {
        const int idx=s->reverse?s->count-1-i:i;
        const Layer *p=&s->layers[idx];
        const int tp=5+(p->depth<<7);
        layer_ctx(&rc,p,1);
        quad(&a,&b,&c,&d,p->uvx,p->uvy);
        HiresAppendQuad(&rc,a,b,c,d,128,128,128,1,tp,31978,p->semi,p->abr);
    }
    /* 64 non-overlapping primitives ensure true worker scheduling for >1. */
    for(f=0;f<64;f++)
        HiresAppendRect(&rc,200+(int)(f%8),200+(int)(f/8),1,1,0,0,0);
    HiresRasterizeThreaded(0,240);
    threaded=s_hires[(size_t)HPY*HSSTRIDE+HPX];
    hash_threaded=hash_region();
    for(i=0;i<(int)BAND_COUNT;i++)
        band_worker[i]=s_hires[(size_t)(BAND_Y[i]*HS)*HSSTRIDE+HPX];
    for(y=0;y<SH*HS;y++)for(x=0;x<SW*HS;x++){
       unsigned short got=s_hires[(size_t)(SY*HS+y)*HSSTRIDE+SX*HS+x];
       if(got!=hd_pixels[y*SW*HS+x]){
           fprintf(stderr,"V52 FAIL HD framebuffer differs scene=%s workers=%d x=%d y=%d direct=%u deferred=%u\n",
             s->name,workers,x,y,(unsigned)hd_pixels[y*SW*HS+x],(unsigned)got);
           return 0;
       }
    }
    for(i=0;i<(int)BAND_COUNT;i++) {
        printf("V52BOUND scene=%s y=%d native=%u direct=%u deferred=%u\n",
          s->name,BAND_Y[i],(unsigned)band_native[i],
          (unsigned)band_direct[i],(unsigned)band_worker[i]);
    }
    printf("V52RESULT scene=%s layers=%d reverse=%d workers=%d background=%u "
           "native=%u direct=%u deferred=%u x=%d y=%d hx=%d hy=%d "
           "directhash=%016llx deferredhash=%016llx pixels=%d\n",
           s->name,s->count,s->reverse,workers,(unsigned)s->background,
           (unsigned)native,(unsigned)direct,(unsigned)threaded,
           PX,PY,HPX,HPY,hash_direct,hash_threaded,(SW*HS)*(SH*HS));
    return direct==threaded&&hash_direct==hash_threaded;
}
int main(void) {
    int i,workers;
    size_t size;
    if(setenv("VH_INTERNAL_SCALE","2",1)!=0||
       setenv("VH_ACCURATE","1",1)!=0) return 2;
    workers=getenv("VH_RASTER_THREADS")?atoi(getenv("VH_RASTER_THREADS")):0;
    if(workers!=1&&workers!=2&&workers!=4) {
      fprintf(stderr,"V52 requires VH_RASTER_THREADS=1,2,4\n");return 2;
    }
    HiresEnsure();
    s_vram=PC_GpuVram();
    s_hires=(const unsigned short *)PC_GpuHiresBytes(&size);
    if(!s_vram||!s_hires||PC_GpuGetInternalScale()!=2||size<2048u*1024u*sizeof(unsigned short))return 2;
    for(i=0;i<N_SCENES;i++)if(!run_scene(&SCENES[i],workers))return 4;
    fprintf(stderr,"V52 ORIGINAL_DDA_LAYERED_SCENES=%d THREADS=%d SYNTHETIC_ONLY\n",N_SCENES,workers);
    return 0;
}
