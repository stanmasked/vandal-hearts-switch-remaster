/*
 * V42 test-only dependency shims for standalone REAL libgpu.c + pc_raster.c.
 * Disabled optional services have no proprietary inputs.
 * Never link into a playable game or replace the production integrations.
 */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
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
/* The test-only trace shim observes the real original DrawOTag's TrcPrim
 * invocation. Production libgpu.c and its original traversal are unchanged.
 * This registry is populated at ADD TIME, not from our expected log. */
#define V54_MAX 384
typedef struct { const void *ptr; int burst,slot,bucket,filler; } V54Entry;
static V54Entry v54_entries[V54_MAX];
static int v54_count=0,v54_seq=0,v54_frame=0;
void V54_Register(const void *ptr,int burst,int slot,int bucket,int filler) {
    V54Entry *e;
    if (v54_count>=V54_MAX) { fprintf(stderr,"V54 trace overflow\n");exit(7); }
    e=&v54_entries[v54_count++];
    e->ptr=ptr;e->burst=burst;e->slot=slot;e->bucket=bucket;e->filler=filler;
}
void TrcPrim(int type, const void *p) {
    int i;
    for(i=0;i<v54_count;i++)
        if(v54_entries[i].ptr==p) {
            fprintf(stdout,
              "V54WALK frame=%d seq=%d burst=%d slot=%d bucket=%d filler=%d type=%d\n",
              v54_frame,v54_seq++,v54_entries[i].burst,v54_entries[i].slot,
              v54_entries[i].bucket,v54_entries[i].filler,type);
            return;
        }
    fprintf(stderr,"V54 FAIL DrawOTag passed unregistered GPU primitive type=%d\n",type);
    exit(8);
}
void TrcFrameEnd(void) {
    fprintf(stdout,"V54TRACE frame=%d count=%d registered=%d\n",
            v54_frame,v54_seq,v54_count);
    v54_frame++;
    v54_seq=0;v54_count=0;
}
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
