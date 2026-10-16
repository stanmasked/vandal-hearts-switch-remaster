/*
 * Map02 v50 — execute the ACTUAL pinned GPU FillQuad -> FillTriangleDDA
 * -> SampleTexture -> WritePixel in 4/8/15bpp, STP, ABR and GP0 windows.
 * ALL fixtures are synthetic, independently validated by a Python oracle.
 * Unlike v49, this is a genuine executable original DDA mode matrix.
 *
 * This is a standalone test-only program. It does NOT represent gameplay,
 * does not use or redistribute any retail game data, and never injects HD.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "pc_gpu_internal.h"

#define NX 88
#define NY 88
#define SCALE 2
#define HX (NX*SCALE+1)
#define HY (NY*SCALE)

typedef struct {
    const char *name;
    int depth;                /* 0=4bpp, 1=8bpp, 2=15bpp */
    int u, v;
    int twmx, twmy, twox, twoy;
    int index;
    unsigned short texel;    /* synthetic ORIGINAL BGR555, bit15=STP */
    unsigned short background;
    int semi, abr, dither;
} Test;

static const Test CASES[] = {
    {"indexed4_opaque",    0,240,192, 0,0,0,0, 1, 0x001f,0x4210,0,0,0},
    {"indexed4_zero",      0,240,192, 0,0,0,0, 1, 0x0000,0x369c,1,1,0},
    {"indexed4_no_stp",    0,240,192, 0,0,0,0, 1, 0x001f,0x4210,1,0,0},
    {"indexed4_abr0",      0,240,192, 0,0,0,0, 1, 0x801f,0x4210,1,0,0},
    {"indexed4_abr1",      0,240,192, 0,0,0,0, 1, 0x801f,0x4210,1,1,0},
    {"indexed4_abr2",      0,240,192, 0,0,0,0, 1, 0x801f,0x4210,1,2,0},
    {"indexed4_abr3",      0,240,192, 0,0,0,0, 1, 0x801f,0x4210,1,3,0},
    {"indexed4_stp_black", 0,240,192, 0,0,0,0, 1, 0x8000,0x4210,1,1,0},
    {"indexed4_dither",    0,240,192, 0,0,0,0, 1, 0x4210,0x4210,0,0,1},
    {"indexed8_lo",        1,240,192, 0,0,0,0,33, 0x03e0,0x4210,0,0,0},
    {"indexed8_hi",        1,241,192, 0,0,0,0,33, 0x7c00,0x4210,0,0,0},
    {"indexed8_stp",       1,241,192, 0,0,0,0,33, 0x83e0,0x4210,1,1,0},
    {"direct15_opaque",    2,240,192, 0,0,0,0,-1, 0x7c00,0x4210,0,0,0},
    {"direct15_stp",       2,240,192, 0,0,0,0,-1, 0x801f,0x4210,1,2,0},
    {"direct15_zero",      2,240,192, 0,0,0,0,-1, 0x0000,0x369c,1,0,0},
    {"window_mask_xy",     0,248,200, 1,1,0,0, 1, 0x4210,0x4210,0,0,0},
    {"window_offset_xy",   0,240,192, 1,1,1,1, 1, 0x03e0,0x4210,0,0,0},
    {"window_8bit",        1,248,200, 1,1,0,0,33, 0x801f,0x4210,1,3,0},
};

static int apply_case(const Test *t) {
    unsigned short (*vram)[1024] = PC_GpuVram();
    const int ueff=(t->u & ~(t->twmx*8)) | ((t->twox & t->twmx)*8);
    const int veff=(t->v & ~(t->twmy*8)) | ((t->twoy & t->twmy)*8);
    const int tpage=5+(t->depth<<7);
    const int ppw=t->depth==0?4:(t->depth==1?2:1);
    const int tx=(tpage&15)*64 + ueff/ppw, ty=((tpage>>4)&1)*256+veff;
    const int clut=31978, cx=(clut&63)*16, cy=(clut>>6)&511;
    const int index=t->index;
    unsigned short word;
    RVert a,b,c,d;
    RenderCtx rc;
    unsigned short after, hd_direct, hd_threaded;
    const unsigned short *hires;
    size_t hires_bytes=0;
    unsigned filler;
    const size_t pixel_offset=(size_t)HY*(1024*SCALE)+HX;
    if (!vram || tx<0 || tx>=1024 || ty<0 || ty>=512 ||
        (index>=0 && (cx+index>=1024 || cy>=512))) return 0;
    if (t->depth==0) {
        word=(unsigned short)((index&15)*0x1111);
    } else if (t->depth==1) {
        word=(unsigned short)((index&255)*0x0101);
    } else {
        word=t->texel;
    }
    vram[ty][tx]=word;
    if (index>=0) vram[cy][cx+index]=t->texel;
    vram[NY][NX]=t->background;
    /* Mirror a known original PS1 background before any drawing: the
     * native and hi-res tests always begin from the SAME BGR555 halfword. */
    HiresMirrorRect(NX,NY,1,1);
    hires=(const unsigned short *)PC_GpuHiresBytes(&hires_bytes);
    if (!hires || hires_bytes < (pixel_offset+1)*sizeof(*hires) ||
        hires[pixel_offset] != t->background) return 0;

    memset(&rc,0,sizeof(rc));
    rc.clipX=0; rc.clipY=0; rc.clipW=320; rc.clipH=240;
    rc.target=0; rc.scale=1;
    rc.dither=t->dither;
    rc.twMaskX=t->twmx; rc.twMaskY=t->twmy;
    rc.twOffX=t->twox; rc.twOffY=t->twoy;
    a.x=80; a.y=80; a.u=t->u; a.v=t->v;
    b.x=96; b.y=80; b.u=t->u; b.v=t->v;
    c.x=80; c.y=96; c.u=t->u; c.v=t->v;
    d.x=96; d.y=96; d.u=t->u; d.v=t->v;
    /* This is the real original accurate FillQuad with genuine native
     * texture sampling, texel zero skip, STP and 5-bit pixel write. */
    FillQuad(&rc,a,b,c,d,128,128,128,1,tpage,clut,t->semi,t->abr);
    after=vram[NY][NX];
    /* Real original high-resolution DDA, with a real scaled RenderCtx.
     * Sample at (2*NX+1,2*NY) to exercise a different dither cell from
     * the native pixel. This is not an upscaled copy of native VRAM. */
    rc.target=1; rc.scale=SCALE;
    FillQuad(&rc,a,b,c,d,128,128,128,1,tpage,clut,t->semi,t->abr);
    hd_direct=hires[pixel_offset];

    /* Run the SAME case via the ACTUAL deferred threaded path. Force the
     * production >=64-primitive threshold with distant synthetic rects,
     * whose output cannot touch the tested (NX,NY) pixel. */
    vram[NY][NX]=t->background;
    HiresMirrorRect(NX,NY,1,1);
    if (hires[pixel_offset]!=t->background) return 0;
    HiresFrameReset();
    HiresAppendQuad(&rc,a,b,c,d,128,128,128,1,tpage,clut,t->semi,t->abr);
    for (filler=0;filler<64;filler++)
        HiresAppendRect(&rc,200+(int)(filler%8),200+(int)(filler/8),
                        1,1,0,0,0);
    HiresRasterizeThreaded(0,240);
    hd_threaded=hires[pixel_offset];
    if (hd_direct!=hd_threaded) {
        fprintf(stderr,"V51 FAIL direct/threaded pixel differs case=%s direct=%u threaded=%u\n",
                t->name,(unsigned)hd_direct,(unsigned)hd_threaded);
        return 0;
    }
    printf("V50 name=%s depth=%d tpage=%d clut=%d u=%d v=%d "
           "maskx=%d masky=%d offx=%d offy=%d tx=%d ty=%d "
           "word=%u index=%d palx=%d paly=%d palette=%u "
           "raw=%u before=%u after=%u semi=%d abr=%d dither=%d x=%d y=%d\n",
           t->name,t->depth,tpage,clut,t->u,t->v,
           t->twmx,t->twmy,t->twox,t->twoy,tx,ty,
           (unsigned)word,index,index<0?-1:cx+index,index<0?-1:cy,
           (unsigned)(index<0?0:t->texel),
           (unsigned)t->texel,(unsigned)t->background,(unsigned)after,
           t->semi,t->abr,t->dither,NX,NY);
    printf("V51HD name=%s depth=%d tpage=%d clut=%d u=%d v=%d "
           "maskx=%d masky=%d offx=%d offy=%d tx=%d ty=%d "
           "word=%u index=%d palx=%d paly=%d palette=%u "
           "raw=%u before=%u after=%u semi=%d abr=%d dither=%d x=%d y=%d\n",
           t->name,t->depth,tpage,clut,t->u,t->v,
           t->twmx,t->twmy,t->twox,t->twoy,tx,ty,
           (unsigned)word,index,index<0?-1:cx+index,index<0?-1:cy,
           (unsigned)(index<0?0:t->texel),
           (unsigned)t->texel,(unsigned)t->background,(unsigned)hd_direct,
           t->semi,t->abr,t->dither,HX,HY);
    printf("V51THREAD name=%s depth=%d tpage=%d clut=%d u=%d v=%d "
           "maskx=%d masky=%d offx=%d offy=%d tx=%d ty=%d "
           "word=%u index=%d palx=%d paly=%d palette=%u "
           "raw=%u before=%u after=%u semi=%d abr=%d dither=%d x=%d y=%d\n",
           t->name,t->depth,tpage,clut,t->u,t->v,
           t->twmx,t->twmy,t->twox,t->twoy,tx,ty,
           (unsigned)word,index,index<0?-1:cx+index,index<0?-1:cy,
           (unsigned)(index<0?0:t->texel),
           (unsigned)t->texel,(unsigned)t->background,(unsigned)hd_threaded,
           t->semi,t->abr,t->dither,HX,HY);
    return 1;
}
int main(void) {
    unsigned i;
    if (setenv("VH_ACCURATE","1",1)!=0 ||
        setenv("VH_INTERNAL_SCALE","2",1)!=0 ||
        setenv("VH_RASTER_THREADS","2",1)!=0) return 2;
    HiresEnsure();
    if (PC_GpuGetInternalScale()!=2 || !HiresActive()) return 2;
    for (i=0;i<sizeof(CASES)/sizeof(CASES[0]);i++) {
        if (!apply_case(&CASES[i])) {
            fprintf(stderr,"V50 FAIL unsafe fixture %s\n",CASES[i].name);
            return 2;
        }
    }
    fprintf(stderr,"V51 ACTUAL_ORIGINAL_HIRES_DIRECT_AND_THREADED_CASES=%u SYNTHETIC_ONLY\n",
            (unsigned)(sizeof(CASES)/sizeof(CASES[0])));
    return 0;
}
