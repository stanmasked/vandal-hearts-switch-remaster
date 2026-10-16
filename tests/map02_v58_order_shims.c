/*
 * V42 test-only dependency shims for standalone REAL libgpu.c + pc_raster.c.
 * Disabled optional services have no proprietary inputs.
 * Never link into a playable game or replace the production integrations.
 */
#include <stddef.h>
#include <stdio.h>
#include "PsyQ/libgpu.h"
#include "pc_gpu_internal.h"

void PC_GpuPresent(unsigned short *vram, int width, int height,
                   int x, int y, int w, int h) {
    (void)vram; (void)width; (void)height;
    (void)x; (void)y; (void)w; (void)h;
}
int PC_CpuCount(void) { return 2; }
void PC_UpdateCamOsd(void) {}
const char *PC_LangBgDir(void) { return NULL; }
void PC_LangPatchFwdUpload(int x, int y, int w, int h, unsigned short *pix) {
    (void)x; (void)y; (void)w; (void)h; (void)pix;
}

void TrcInit(void) {}
void TrcWrite(char op, const void *a, u32 na, const void *b, u32 nb) {
    (void)op; (void)a; (void)na; (void)b; (void)nb;
}
static const char *v58_current_case;
static int v58_position;
void V58_BeginCase(const char *name) {
    v58_current_case=name;
    v58_position=0;
}
void TrcPrim(int type, const void *p) {
    if (!v58_current_case) return;
    if(type==PC_GPU_PRIM_DR_MASK){
        const DR_MASK *m=(const DR_MASK *)p;
        printf("V58OT name=%s index=%d type=mask command=%u\\n",
               v58_current_case,v58_position++,(unsigned)m->command);
    }else if(type==PC_GPU_PRIM_POLY_FT4){
        const POLY_FT4 *q=(const POLY_FT4 *)p;
        printf("V58OT name=%s index=%d type=quad uv=%u semi=%d abr=%d\\n",
               v58_current_case,v58_position++,(unsigned)q->u0,
               PC_GPU_IS_SEMI((const P_TAG *)p)?1:0,(q->tpage>>5)&3);
    }
}
void TrcFrameEnd(void) {}
int TrcReplaying(void) { return 0; }

void HdPack_OnLoad(const RECT *r, const unsigned short *p) {
    (void)r; (void)p;
}
void HdMaybeDump(int tpage, int clut, int u0, int u1, int v0, int v1) {
    (void)tpage; (void)clut; (void)u0; (void)u1; (void)v0; (void)v1;
}
HdRegion *HdFindTriRegion(int tpage, int u0, int u1, int v0, int v1) {
    (void)tpage; (void)u0; (void)u1; (void)v0; (void)v1;
    return NULL;
}
int HdActive(void) { return 0; }
int HdAnyActive(void) { return 0; }
const char *HdDumpDir(void) { return NULL; }
int HdRegionCount(void) { return 0; }
int HdReplaceCount(void) { return 0; }
