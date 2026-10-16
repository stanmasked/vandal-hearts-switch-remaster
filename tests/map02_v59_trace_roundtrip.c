/*
 * v59: actual pinned PC-port VHT1 GPU recorder and replay driver.
 * Only synthetic patterns, no retail M_MAP02.PRS or copyrighted data.
 *
 * Record: real LoadImage/PutDrawEnv/ClearOTag/AddPrim/DrawOTag/TrcPrim
 * writes a VHT1 binary with interleaved synthetic PC-port E6 OT packets.
 * Replay: real PC_GpuReplayTrace reads that file and re-executes original GPU.
 * Run record and replay in DIFFERENT processes (fresh static GPU state).
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
#define FILLERS 64
#define NFRAMES 4
#define MAX_STEPS 4

typedef struct { unsigned command,texel; int semi; } Step;
typedef struct {
    const char *name;
    unsigned short bg;
    int cx,cy,cw,ch,abr,n;
    Step step[MAX_STEPS];
} Frame;
static const Frame frames[NFRAMES]={
    {"mark_skip",0x0010,0,0,320,240,0,2,
        {{0xe6000001u,0x001fu,0},{0xe6000002u,0x03e0u,0}}},
    {"reopen",0x0010,0,0,320,240,0,4,
        {{0xe6000001u,0x001fu,0},{0xe6000002u,0x03e0u,0},
         {0xe6000000u,0x7c00u,0},{0xe6000002u,0x03e0u,0}}},
    {"stp_abr2",0x0010,0,0,320,240,2,3,
        {{0xe6000001u,0x001fu,0},{0xe6000000u,0x7c00u,0},
         {0xe6000002u,0x83e0u,1}}},
    {"clip_mask",0x0010,75,74,10,12,0,2,
        {{0xe6000001u,0x001fu,0},{0xe6000003u,0x83e0u,1}}}
};
typedef struct {
    DR_MODE mode;
    DR_MASK mask[MAX_STEPS];
    POLY_FT4 quad[MAX_STEPS];
    TILE filler[FILLERS];
    u32 ot[8];
} Packet;
static unsigned short bgwords[W*H];
static unsigned short texwords[MAX_STEPS];

/* Matches original pc_gpu_trace.c TrcVramHash / TrcHiresHash byte order. */
static unsigned long long bytes_hash(const void *data,size_t bytes){
    const unsigned char *p=(const unsigned char *)data;
    unsigned long long h=1469598103934665603ull;
    size_t i;
    for(i=0;i<bytes;i++){h^=p[i];h*=1099511628211ull;}
    return h;
}
static void emit_hash(int frame){
    size_t nb=0,nh=0;
    const void *vram=PC_GpuVramBytes(&nb);
    const void *hd=PC_GpuHiresBytes(&nh);
    if(!vram||!hd||nb!=(size_t)1024*512*2||
       nh!=(size_t)2048*1024*2){
        fprintf(stderr,"V59 ERROR native/2x framebuffer unavailable\n");
        exit(3);
    }
    printf("V59FRAME phase=record frame=%d nativehash=%016llx hihash=%016llx\n",
           frame,bytes_hash(vram,nb),bytes_hash(hd,nh));
}
static void build(Packet *p,const Frame *f){
    RECT win;
    int i;
    memset(p,0,sizeof(*p));
    setRECT(&win,0,0,256,256);
    SetDrawMode(&p->mode,0,0,GetTPage(2,f->abr,448,0),&win);
    for(i=0;i<f->n;i++){
        PC_SetDrawMaskPacket(&p->mask[i],f->step[i].command);
        SetPolyFT4(&p->quad[i]);
        setRGB0(&p->quad[i],128,128,128);
        setXYWH(&p->quad[i],70,70,20,20);
        setUVWH(&p->quad[i],20+i,192,0,0);
        p->quad[i].tpage=GetTPage(2,f->abr,448,0);
        p->quad[i].clut=0;
        SetSemiTrans(&p->quad[i],f->step[i].semi);
    }
    for(i=0;i<FILLERS;i++){
        SetTile(&p->filler[i]);
        setRGB0(&p->filler[i],0,0,0);
        setXY0(&p->filler[i],250+i%8,204+i/8);
        setWH(&p->filler[i],1,1);
    }
    ClearOTag(p->ot,8);
    for(i=FILLERS-1;i>=0;i--)AddPrim(&p->ot[7],&p->filler[i]);
    for(i=f->n-1;i>=0;i--){
        AddPrim(&p->ot[0],&p->quad[i]);
        AddPrim(&p->ot[0],&p->mask[i]);
    }
    AddPrim(&p->ot[0],&p->mode);
}
static int record(const char *path){
    int frame,i;
    DISPENV disp;
    RECT area,source;
    unsigned (*unused)[2] = NULL;
    (void)unused;
    if(!getenv("VH_GPU_RECORD") || strcmp(getenv("VH_GPU_RECORD"),path)!=0){
        fprintf(stderr,"V59 ERROR VH_GPU_RECORD must equal output filename\n");
        return 2;
    }
    if(!getenv("VH_GPU_RECORD_FRAMES") ||
       atoi(getenv("VH_GPU_RECORD_FRAMES"))!=NFRAMES){
        fprintf(stderr,"V59 ERROR VH_GPU_RECORD_FRAMES must equal 4\n");
        return 2;
    }
    HiresEnsure();
    if(PC_GpuGetInternalScale()!=2)return 2;
    SetDefDispEnv(&disp,0,0,320,240);
    PutDispEnv(&disp);
    setRECT(&area,X,Y,W,H);
    setRECT(&source,468,192,MAX_STEPS,1);
    for(frame=0;frame<NFRAMES;frame++){
        const Frame *f=&frames[frame];
        Packet p;
        DRAWENV env;
        for(i=0;i<W*H;i++)bgwords[i]=f->bg;
        for(i=0;i<MAX_STEPS;i++)
            texwords[i]=(unsigned short)(i<f->n?f->step[i].texel:0u);
        /* Unlike direct VRAM writes these genuine API uploads get captured as
         * VHT1 'L' operations for deterministic replay source/background. */
        LoadImage(&area,(unsigned int *)bgwords);
        LoadImage(&source,(unsigned int *)texwords);
        SetDefDrawEnv(&env,0,0,320,240);
        env.clip.x=f->cx;env.clip.y=f->cy;
        env.clip.w=f->cw;env.clip.h=f->ch;
        env.dtd=0;
        PutDrawEnv(&env);
        if(!PC_GpuGp0MaskE6(0xe6000000u))return 2;
        build(&p,f);
        DrawOTag(p.ot);
        emit_hash(frame);
    }
    fprintf(stderr,"V59 RECORDED_VHT1_FRAMES=%d SYNTHETIC_ONLY\n",NFRAMES);
    return 0;
}
int PC_GpuReplayTrace(const char *path);
int main(int argc,char **argv){
    if(argc!=3){
        fprintf(stderr,"usage: v59_original_trace [record|replay] TRACE_FILE\n");
        return 2;
    }
    if(strcmp(argv[1],"record")==0)return record(argv[2]);
    if(strcmp(argv[1],"replay")==0)return PC_GpuReplayTrace(argv[2]);
    return 2;
}
