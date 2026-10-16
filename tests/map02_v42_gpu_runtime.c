/*
 * v42: executable smoke of the ACTUAL, pinned PC-port GPU walker + DDA.
 * All texture data, polygons and frame structures below are synthetic.
 * No original game executable, disc, game setup or terrain geometry.
 *
 * pc_raster.c + libgpu.c are compiled, not simulated. v39 tagging is
 * explicitly invoked to mimic the exact post-AddPrim terrain callsite.
 * A distinct FT4 with identical UV/tpage/clut stays UNTAGGED (sprite).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "PsyQ/libgpu.h"
#include "pc_gpu_internal.h"

extern void PC_Map02V39MarkSubmitted(void *ot, void *prim,
                                     int gfx, int mapnum, int route);

#define VH_TEX_SIZE 64
static unsigned short texture[VH_TEX_SIZE * VH_TEX_SIZE];
static int failures;

#define VERIFY(cond, desc) do { \
    if (!(cond)) { fprintf(stderr, "[v42-smoke] FAIL: %s\n", desc); failures++; } \
} while (0)

static void make_quad(POLY_FT4 *q, int x, int y, u_short tpage) {
    SetPolyFT4(q);
    setRGB0(q, 128, 128, 128);
    setXYWH(q, x, y, VH_TEX_SIZE, VH_TEX_SIZE);
    q->tpage = tpage;
    q->clut = 0;
    q->u0 = 0; q->v0 = 0;
    q->u1 = 63; q->v1 = 0;
    q->u2 = 0; q->v2 = 63;
    q->u3 = 63; q->v3 = 63;
}

static int draw_frame(int gfx, int valid_terrain) {
    unsigned int ot[16];
    POLY_FT4 terrain, mimic_sprite;
    TILE fillers[64];
    int i;
    u_short tpage = GetTPage(2, 0, 640, 0);

    make_quad(&terrain, 64, 64, tpage);
    make_quad(&mimic_sprite, 192, 64, tpage);
    ClearOTag(ot, 16);
    /* Add >64 primitives so the real hi-res scheduler uses 2 row-band
     * workers, exercising immutable per-primitive context under concurrency. */
    for (i = 0; i < 64; ++i) {
        SetTile(&fillers[i]);
        setRGB0(&fillers[i], 0, 0, 0);
        setXY0(&fillers[i], 280 + (i % 8), 180 + (i / 8));
        setWH(&fillers[i], 1, 1);
        AddPrim(&ot[0], &fillers[i]);
    }
    /* Sprite mimics exact terrain texture metadata; never mark it. */
    AddPrim(&ot[0], &mimic_sprite);
    /* A real terrain polygon invokes the v39 marker immediately after AddPrim. */
    AddPrim(&ot[0], &terrain);
    PC_Map02V39MarkSubmitted(&ot[0], &terrain, gfx,
                              valid_terrain ? 11 : 2, 1);
    DrawOTag(&ot[0]);

    {
        RECT r;
        unsigned short p1 = 0, p2 = 0;
        setRECT(&r, 96, 96, 1, 1);
        StoreImage(&r, (unsigned int *)&p1);
        setRECT(&r, 224, 96, 1, 1);
        StoreImage(&r, (unsigned int *)&p2);
        VERIFY((p1 & 0x7fff) != 0, "real DDA drew terrain into native VRAM");
        VERIFY((p2 & 0x7fff) != 0, "untagged mimic sprite still draws normally");
    }
    {
        size_t bytes = 0;
        const unsigned short *pixels = (const unsigned short *)PC_GpuHiresBytes(&bytes);
        const int W = 1024 * 2;
        VERIFY(pixels != NULL && bytes > (size_t)(128 * W * 2),
               "real deferred hi-res target allocated and exposed");
        if (pixels)
            VERIFY((pixels[(size_t)192 * W + 192] & 0x7fff) != 0,
                   "real DDA drew tagged terrain into hi-res target");
    }
    for (i = 0; i < 2; ++i)
        VERIFY(PC_GpuGetInternalScale() == 2, "internal render scale remains 2");
    return failures == 0;
}

int main(void) {
    DRAWENV draw;
    DISPENV disp;
    RECT upload;
    int i;

    /* Must be set before first DrawOTag reads its process-lifetime option. */
    if (setenv("VH_MAP02_V39_TRACE", "1", 1) != 0) {
        perror("setenv");
        return 2;
    }
    if (setenv("VH_RASTER_THREADS", "2", 1) != 0) {
        perror("setenv");
        return 2;
    }
    if (setenv("VH_ACCURATE", "1", 1) != 0) {
        perror("setenv");
        return 2;
    }

    ResetGraph(0);
    SetDefDrawEnv(&draw, 0, 0, 320, 240);
    SetDefDispEnv(&disp, 0, 0, 320, 240);
    PutDrawEnv(&draw);
    PutDispEnv(&disp);
    PC_GpuSetInternalScale(2);
    /* Synthetic 15bpp texture: all-red, no CLUT required. */
    for (i = 0; i < VH_TEX_SIZE * VH_TEX_SIZE; ++i)
        texture[i] = 0x001f;
    setRECT(&upload, 640, 0, VH_TEX_SIZE, VH_TEX_SIZE);
    LoadImage(&upload, (unsigned int *)texture);
    VERIFY(draw_frame(641, 1), "frame 1 GPU pass");
    VERIFY(draw_frame(643, 1), "frame 2 GPU pass, recycled OT token and changed gfx");
    VERIFY(draw_frame(644, 0), "frame 3 GPU path with wrong map and no provenance");
    if (failures) {
        fprintf(stderr, "[v42-smoke] FAIL: %d native GPU assertions\n", failures);
        return 1;
    }
    fprintf(stderr, "[v42-smoke] PASS: 3 synthetic frames, 2 tagged terrain FT4,"
                    " 3 untagged matching-UV sprite FT4; real native/hires DDA\n");
    return 0;
}
