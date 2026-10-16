/*
 * V43: run the ORIGINAL src/core/graphics.c RenderMapTile() against the
 * ORIGINAL public PC-port libgte.c, libgpu.c and pc_raster.c.
 *
 * Synthetic face/texture/data; NO original game assets and no game logic
 * outside RenderMapTile. This is a GPU/GTE/terrain-producer integration smoke.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "common.h"
#include "graphics.h"
#include "field.h"
#include "state.h"
#include "PsyQ/libgte.h"
#include "PsyQ/libgpu.h"
#include "pc_gpu_internal.h"

/* Production graphics globals supplied by generated game data in real builds.
 * V43 defines only the ones consumed by RenderMapTile and its v39 hook. */
static Graphics s_v43Graphics;
Graphics *gGraphicsPtr = &s_v43Graphics;
s32 gQuadIndex;
CVECTOR gSideLightColor[26];
s16 gGfxClutIds[GFX_CT];
s16 gGfxTPageIds[GFX_CT];
u8 gGfxSubTextures[GFX_CT][4];
State gState;
MapTileModel *gMapRowPointers[28];
static MapTileModel s_row[28];

static unsigned short s_texture[64 * 64];
static int s_failures;
#define V43_CHECK(c,what) do { \
    if (!(c)) { fprintf(stderr, "[v43] FAIL: %s\n", what); ++s_failures; } \
} while (0)

static unsigned long long v43_hash(const void *buf, size_t len) {
    const unsigned char *p = (const unsigned char *)buf;
    unsigned long long h = 1469598103934665603ull;
    size_t i;
    for (i = 0; i < len; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

static void setup_model(void) {
    MapTileModel *t = &s_row[19];
    int i;
    memset(s_row, 0, sizeof(s_row));
    gMapRowPointers[8] = s_row;
    t->faceCt = 1;
    t->gfx[0] = 641;
    t->shades[0] = 0;
    t->faces[0][0] = 0; t->faces[0][1] = 1;
    t->faces[0][2] = 2; t->faces[0][3] = 3;
    /* Front-facing square with positive Z; real GTE projects it at 96..160. */
    t->vertices[0].vx = 0;  t->vertices[0].vy = 0;
    t->vertices[1].vx = 64; t->vertices[1].vy = 0;
    t->vertices[2].vx = 64; t->vertices[2].vy = 64;
    t->vertices[3].vx = 0;  t->vertices[3].vy = 64;
    for (i = 0; i < 4; ++i) t->vertices[i].vz = 1000;
    for (i = 641; i <= 644; ++i) {
        gGfxClutIds[i] = 0;
        gGfxTPageIds[i] = GetTPage(2, 0, 640, 0);
        gGfxSubTextures[i][0] = 0;
        gGfxSubTextures[i][1] = 0;
        gGfxSubTextures[i][2] = 63;
        gGfxSubTextures[i][3] = 63;
    }
    gSideLightColor[0].r = 128;
    gSideLightColor[0].g = 128;
    gSideLightColor[0].b = 128;
    InitGeom(); /* REAL PC GTE, no projected vertices precomputed. */
    SetGeomOffset(96, 96);
    SetGeomScreen(1000);
}

static void make_spoof(POLY_FT4 *q) {
    SetPolyFT4(q);
    setRGB0(q, 128, 128, 128);
    setXYWH(q, 192, 64, 64, 64);
    q->tpage = GetTPage(2, 0, 640, 0);
    q->clut = 0;
    q->u0 = 0;  q->v0 = 0;
    q->u1 = 63; q->v1 = 0;
    q->u2 = 0;  q->v2 = 63;
    q->u3 = 63; q->v3 = 63;
}

static void draw_one_frame(int frame, int mapnum, int gfx) {
    unsigned int *ot = s_v43Graphics.ot;
    TILE fillers[64];
    POLY_FT4 sprite;
    RECT sample;
    unsigned short px = 0, spr = 0;
    size_t hires_size = 0;
    const unsigned short *hires;
    int i, stride;

    gState.mapNum = (u8)mapnum;
    gState.frameCounter = frame;
    gQuadIndex = 0;
    s_row[19].gfx[0] = gfx;
    ClearOTag(ot, OT_SIZE);
    for (i = 0; i < 64; ++i) {
        SetTile(&fillers[i]);
        setRGB0(&fillers[i], 0, 0, 0);
        setXY0(&fillers[i], 280 + (i % 8), 180 + (i / 8));
        setWH(&fillers[i], 1, 1);
        AddPrim(&ot[0], &fillers[i]);
    }
    make_spoof(&sprite);
    AddPrim(&ot[0], &sprite);
    /* This call produces its own projected POLY_FT4 from SVECTOR vertices,
       calculates GTE back-face and OT depth, then calls the real AddPrim. */
    RenderMapTile(ot, &s_row[19], GRID_COLOR_NONE);
    V43_CHECK(gQuadIndex == 1, "real RenderMapTile submitted exactly one FT4");
    V43_CHECK(s_v43Graphics.quads[0].tpage == GetTPage(2,0,640,0),
              "game code resolved synthetic GFX to original texture page");
    V43_CHECK(s_v43Graphics.quads[0].x0 < s_v43Graphics.quads[0].x1,
              "real GTE projected positive horizontal screen edge");
    V43_CHECK(s_v43Graphics.quads[0].y0 < s_v43Graphics.quads[0].y2,
              "real GTE projected positive vertical screen edge");
    DrawOTag(ot);
    setRECT(&sample, 128, 128, 1, 1);
    StoreImage(&sample, (unsigned int *)&px);
    setRECT(&sample, 224, 96, 1, 1);
    StoreImage(&sample, (unsigned int *)&spr);
    V43_CHECK((px & 0x7fff) != 0, "real game tile emitted visible native pixel");
    V43_CHECK((spr & 0x7fff) != 0, "UV-identical unrelated FT4 still draws");
    hires = (const unsigned short *)PC_GpuHiresBytes(&hires_size);
    stride = 1024 * PC_GpuGetInternalScale();
    V43_CHECK(hires && hires_size > 0, "real deferred hi-res buffer is present");
    if (hires)
        V43_CHECK((hires[(size_t)256 * stride + 256] & 0x7fff) != 0,
                  "real projected tile visible in hi-res buffer");
}

int main(void) {
    DRAWENV draw;
    DISPENV disp;
    RECT tex;
    size_t n_native = 0, n_hires = 0;
    const void *native, *hires;
    int i;

    if (setenv("VH_MAP02_V39_TRACE", "1", 1) != 0 ||
        setenv("VH_ACCURATE", "1", 1) != 0) return 2;
    if (!getenv("VH_RASTER_THREADS") &&
        setenv("VH_RASTER_THREADS", "2", 1) != 0) return 2;
    ResetGraph(0);
    SetDefDrawEnv(&draw, 0, 0, 320, 240);
    SetDefDispEnv(&disp, 0, 0, 320, 240);
    PutDrawEnv(&draw);
    PutDispEnv(&disp);
    PC_GpuSetInternalScale(2);
    for (i = 0; i < 64 * 64; ++i) s_texture[i] = 0x001f;
    setRECT(&tex, 640, 0, 64, 64);
    LoadImage(&tex, (unsigned int *)s_texture);

    setup_model();
    draw_one_frame(1, 11, 641);
    draw_one_frame(2, 11, 643);
    draw_one_frame(3, 2, 644);  /* wrong map: still draws, not tagged */

    if (s_failures) {
        fprintf(stderr, "[v43] FAIL: %d assertions\n", s_failures);
        return 1;
    }
    native = PC_GpuVramBytes(&n_native);
    hires = PC_GpuHiresBytes(&n_hires);
    V43_CHECK(native && hires && n_native && n_hires, "GPU framebuffers readable");
    if (s_failures) return 1;
    fprintf(stderr, "[v43] FRAMEBUFFER_HASH native=%016llx hires=%016llx\n",
            v43_hash(native, n_native), v43_hash(hires, n_hires));
    fprintf(stderr, "[v43] PASS real graphics.c RenderMapTile → libgte.c projection → "
                    "libgpu.c DrawOTag → pc_raster.c DDA; three SYNTHETIC frames\n");
    return 0;
}
