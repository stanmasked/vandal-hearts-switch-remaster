/*
 * V42 test-only dependency shims for standalone REAL libgpu.c + pc_raster.c.
 * Disabled optional services have no proprietary inputs.
 * Never link into a playable game or replace the production integrations.
 */
#include <stddef.h>
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
void TrcPrim(int type, const void *p) { (void)type; (void)p; }
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
