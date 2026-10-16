/*
 * v53 ACTUAL pinned PC-port ClearOTag -> AddPrim -> DrawOTag, with
 * mixed TILE, FT4 (4bpp/15bpp), DR_MODE, SPRT (8bpp) and untextured F4.
 * Original GPU source is UNMODIFIED. Everything here is SYNTHETIC.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define X 80
#define Y 40
#define W 16
#define H 160
#define S 2
#define PX 88
#define PY 88
#define NPX 177
#define NPY 176
#define ROW 2048
#define COUNT 8
#define BURSTS 24
#define DEPTH_BUCKETS 4
#define FILLERS 64
#define TOTAL_PACKETS (BURSTS*COUNT+FILLERS)
enum { RESET, TILE_BG, TEX4, MODE_SPRT, SPRITE8, MODE_F4, F4_SEMI, TEX15 };
static const int SEQS[2][COUNT] = {
  {RESET,TILE_BG,TEX4,MODE_SPRT,SPRITE8,MODE_F4,F4_SEMI,TEX15},
  {RESET,TILE_BG,TEX15,MODE_SPRT,SPRITE8,MODE_F4,F4_SEMI,TEX4}
};
typedef struct {
  DR_MODE reset, sprt_mode, f4_mode;
  POLY_FT4 tex4,tex15;
  POLY_F4 f4;
  SPRT sprt;
  TILE tile,fillers[FILLERS];
  u32 ot[8];
} ScenePrims;
static unsigned short (*vram)[1024];
static const unsigned short *hires;
static unsigned short saved[W*S*H*S];
/* Test-only observed actual DrawOTag walk. Hook is in the optional trace shim,
 * not libgpu.c; production source stays identical to pinned upstream. */
void V54_Register(const void *p,int burst,int slot,int bucket,int filler);


static void populate(void) {
    int x,y;
    RECT dummy;
    (void)dummy;
    for(y=0;y<192;y++)for(x=384;x<448;x++)vram[y][x]=0x0202;
    for(y=56;y<64;y++)for(x=404;x<408;x++)vram[y][x]=0x0101;
    vram[192][372]=0x1111; /* 4bpp texture u=208, v=192: index1 */
    vram[192][468]=0x801f; /* 15bpp texture u=20, v=192 with STP */
    vram[499][(31978&63)*16+1]=0x801f; /* red STP 4bpp, enables 24-layer order-sensitive compositing */
    vram[498][(31914&63)*16+1]=0x83e0; /* green + STP 8bpp */
    vram[498][(31914&63)*16+2]=0x801f; /* red + STP 8bpp */
}
static void clear_target(void) {
  int x,y;
  for(y=Y;y<Y+H;y++)for(x=X;x<X+W;x++)vram[y][x]=0;
  HiresMirrorRect(X,Y,W,H);
}
static void q4(RVert *a,RVert *b,RVert *c,RVert *d,int u,int v,int sprite) {
  a->x=X;a->y=Y;a->u=u;a->v=v;
  b->x=X+W;b->y=Y;b->u=sprite?u+W:u;b->v=v;
  c->x=X;c->y=Y+H;c->u=u;c->v=sprite?v+H:v;
  d->x=X+W;d->y=Y+H;d->u=sprite?u+W:u;d->v=sprite?v+H:v;
}
static void init_prims(ScenePrims *p,int burst) {
  RECT full,window;
  int i;
  memset(p,0,sizeof(*p));
  setRECT(&full,0,0,256,256);
  setRECT(&window,8,8,248,248); /* texture-window mask=1, offset=1 */
  SetDrawMode(&p->reset,0,0,GetTPage(0,0,320,0),&full);
  SetDrawMode(&p->sprt_mode,0,0,GetTPage(1,1,384,0),&window);
  SetDrawMode(&p->f4_mode,0,0,GetTPage(0,3,320,0),&full);
  SetTile(&p->tile);setRGB0(&p->tile,40,64,88);
  setXY0(&p->tile,burst==0?X:300,Y);setWH(&p->tile,W,H);
  SetPolyFT4(&p->tex4);setRGB0(&p->tex4,128,128,128);
  setXYWH(&p->tex4,X,Y,W,H);setUVWH(&p->tex4,208,192,0,0);
  p->tex4.tpage=GetTPage(0,0,320,0);
  p->tex4.clut=GetClut(672,499);SetSemiTrans(&p->tex4,1);
  SetPolyFT4(&p->tex15);setRGB0(&p->tex15,128,128,128);
  setXYWH(&p->tex15,X,Y,W,H);setUVWH(&p->tex15,20,192,0,0);
  p->tex15.tpage=GetTPage(2,2,448,0);
  p->tex15.clut=0;SetSemiTrans(&p->tex15,1);
  SetSprt(&p->sprt);setRGB0(&p->sprt,128,128,128);
  setXY0(&p->sprt,X,Y);setWH(&p->sprt,W,H);
  p->sprt.u0=24;p->sprt.v0=0;p->sprt.clut=GetClut(672,498);
  SetSemiTrans(&p->sprt,1);
  SetPolyF4(&p->f4);setRGB0(&p->f4,128,0,128);
  setXYWH(&p->f4,X,Y,W,H);SetSemiTrans(&p->f4,1);
  for(i=0;i<FILLERS;i++) {
    SetTile(&p->fillers[i]);setRGB0(&p->fillers[i],0,0,0);
    setXY0(&p->fillers[i],250+i%8,201+i/8);
    setWH(&p->fillers[i],1,1);
  }
}
static void *packet(ScenePrims *p,int id) {
  switch(id) {
    case RESET:return &p->reset;
    case TILE_BG:return &p->tile;
    case TEX4:return &p->tex4;
    case MODE_SPRT:return &p->sprt_mode;
    case SPRITE8:return &p->sprt;
    case MODE_F4:return &p->f4_mode;
    case F4_SEMI:return &p->f4;
    default:return &p->tex15;
  }
}
static void append_ot(ScenePrims *p,int scene) {
  int i,k,id,bucket;
  ClearOTag(p[0].ot,8);
  /* Head insertion reverses each bucket; insert filler packets in reverse
   * to make the actual DrawOTag trace increasing index, just like the four
   * depth-sorted semantic buckets. */
  for(i=FILLERS-1;i>=0;i--){
    V54_Register(&p[0].fillers[i],-1,i,7,1);
    AddPrim(&p[0].ot[7],&p[0].fillers[i]);
  }
  /* Insert backwards within each OT bucket so the actual LIFO AddPrim
   * yields ascending (burst, semantic packet), with real depth ordering
   * across buckets 0..3. The 64 fillers occupy bucket 7. */
  for(k=BURSTS-1;k>=0;k--)
    for(i=COUNT-1;i>=0;i--) {
      id=SEQS[scene][i];
      bucket=k/(BURSTS/DEPTH_BUCKETS);
      V54_Register(packet(&p[k],id),k,i,bucket,0);
      AddPrim(&p[0].ot[bucket],packet(&p[k],id));
    }
}
static unsigned long long hash_hires(void) {
  unsigned long long h=1469598103934665603ull;
  int x,y;
  for(y=Y*S;y<(Y+H)*S;y++)for(x=X*S;x<(X+W)*S;x++){
    h ^= hires[(size_t)y*ROW+x];
    h *=1099511628211ull;
  }
  return h;
}
static void draw_manual(int id,RenderCtx *rc,int burst) {
  RVert a,b,c,d;
  RECT window;
  switch(id){
    case RESET:
      rc->twMaskX=rc->twMaskY=rc->twOffX=rc->twOffY=0;
      rc->dither=0;break;
    case TILE_BG:if(burst==0)FillRect(rc,X,Y,W,H,40,64,88);break;
    case TEX4:
      q4(&a,&b,&c,&d,208,192,0);
      FillQuad(rc,a,b,c,d,128,128,128,1,GetTPage(0,0,320,0),
               GetClut(672,499),1,0);break;
    case MODE_SPRT:
      rc->twMaskX=rc->twMaskY=rc->twOffX=rc->twOffY=1;break;
    case SPRITE8:
      q4(&a,&b,&c,&d,24,0,1);
      FillQuad(rc,a,b,c,d,128,128,128,1,GetTPage(1,1,384,0),
               GetClut(672,498),1,1);break;
    case MODE_F4:
      rc->twMaskX=rc->twMaskY=rc->twOffX=rc->twOffY=0;break;
    case F4_SEMI:
      q4(&a,&b,&c,&d,0,0,0);
      FillQuad(rc,a,b,c,d,128,0,128,0,0,0,1,3);break;
    case TEX15:
      q4(&a,&b,&c,&d,20,192,0);
      FillQuad(rc,a,b,c,d,128,128,128,1,GetTPage(2,2,448,0),0,1,2);break;
  }
}
static int run_scene(int scene,int workers) {
  ScenePrims p[BURSTS];
  DISPENV disp;
  DRAWENV env;
  RenderCtx rc;
  unsigned short native,hd,manual;
  unsigned long long hdhash,manualhash;
  int i,x,y;
  populate();
  for(i=0;i<BURSTS;i++) init_prims(&p[i],i);
  clear_target();
  SetDefDrawEnv(&env,0,0,320,240);
  env.dtd=0;
  PutDrawEnv(&env);
  SetDefDispEnv(&disp,0,0,320,240);
  PutDispEnv(&disp);
  append_ot(p,scene);
  DrawOTag(p[0].ot);
  native=vram[PY][PX];
  hd=hires[(size_t)NPY*ROW+NPX];
  hdhash=hash_hires();
  for(y=0;y<H*S;y++)for(x=0;x<W*S;x++)
    saved[y*W*S+x]=hires[(size_t)(Y*S+y)*ROW+X*S+x];
  clear_target();
  memset(&rc,0,sizeof(rc));
  rc.clipX=0;rc.clipY=0;rc.clipW=320;rc.clipH=240;
  rc.target=1;rc.scale=2;
  { int k; for(k=0;k<BURSTS;k++) for(i=0;i<COUNT;i++) draw_manual(SEQS[scene][i],&rc,k); }
  manual=hires[(size_t)NPY*ROW+NPX];
  manualhash=hash_hires();
  for(y=0;y<H*S;y++)for(x=0;x<W*S;x++){
    unsigned short actual=hires[(size_t)(Y*S+y)*ROW+X*S+x];
    if(actual!=saved[y*W*S+x]){
      fprintf(stderr,"V53 FAIL real DrawOTag vs manual original GPU x=%d y=%d scene=%d worker=%d got=%u expected=%u\n",
        x,y,scene,workers,(unsigned)saved[y*W*S+x],(unsigned)actual);
      return 0;
    }
  }
  printf("V54SUMMARY scene=%d workers=%d bursts=%d buckets=%d packets=%d native=%u hires=%u direct=%u "
         "othash=%016llx directhash=%016llx pixels=%d clut4=%u clut8=%u "
         "sprite_tpage=%u sprite_mask=1 sprite_offset=1\n",
    scene,workers,BURSTS,DEPTH_BUCKETS,TOTAL_PACKETS,(unsigned)native,(unsigned)hd,(unsigned)manual,
    hdhash,manualhash,W*S*H*S,(unsigned)GetClut(672,499),
    (unsigned)GetClut(672,498),(unsigned)GetTPage(1,1,384,0));
  return hdhash==manualhash && hd==manual;
}
int main(void) {
  int scene,workers;
  size_t size=0;
  workers=getenv("VH_RASTER_THREADS")?atoi(getenv("VH_RASTER_THREADS")):0;
  if(workers!=1&&workers!=2&&workers!=4) return 2;
  if(setenv("VH_INTERNAL_SCALE","2",1)!=0||setenv("VH_ACCURATE","1",1)!=0)return 2;
  HiresEnsure();
  vram=PC_GpuVram();
  hires=(const unsigned short *)PC_GpuHiresBytes(&size);
  if(!vram||!hires||PC_GpuGetInternalScale()!=2||size<2048u*1024u*2)return 2;
  for(scene=0;scene<2;scene++)if(!run_scene(scene,workers))return 3;
  fprintf(stderr,"V54 ORIGINAL_DRAWOTAG_LARGE_SCENES=2 PACKETS=256 WORKERS=%d SYNTHETIC_ONLY\n",workers);
  return 0;
}
