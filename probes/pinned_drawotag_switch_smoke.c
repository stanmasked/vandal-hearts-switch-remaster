/* Asset-free integration probe for the ORIGINAL pinned PC-port DrawOTag.
 * Uses the genuine ordering-table API + software rasterizer + PC_GpuPresent.
 * Stub hooks below are strictly test-only: no original game loop/assets.
 */
#include <SDL2/SDL.h>
#include <stdio.h>
#include <signal.h>
#include "PsyQ/libgpu.h"
#include "pc_gpu_internal.h"
#include "pc_platform.h"
#include "switch_sdl2_observer_backend.h"

extern int PC_GpuInit(int width, int height, const char *title);
extern void PC_GpuGetWindowSize(int *width, int *height, int *scale);

static void tile(TILE *out, short x, short y, short w, short h,
                 unsigned char r, unsigned char g, unsigned char b) {
    SetTile(out);
    setXY0(out, x, y);
    setWH(out, w, h);
    setRGB0(out, r, g, b);
}

/* The original OT walker draws newest-inserted first. Insert the four
 * corner tiles first and the full-screen background last, so corners
 * cover the background during real DrawOTag rasterization. */
static void draw_frame(int frame) {
    DRAWENV draw;
    DISPENV display;
    unsigned int ot[1];
    TILE corner[4], background;
    POLY_F4 polygon;
    POLY_FT4 textured;
    /* 4bpp: four texels (1,2,1,2) per packed 16-bit VRAM word. */
    unsigned short texels[2] = {0x2121, 0x2121};
    unsigned short palette[16] = {0, 0x001f, 0x03e0};
    RECT tex_rect, clut_rect;
    SetDefDrawEnv(&draw, 0, 0, 12, 9);
    SetDefDispEnv(&display, 0, 0, 12, 9);
    PutDrawEnv(&draw);
    PutDispEnv(&display);
    /* Upload to off-screen VRAM through the ORIGINAL LoadImage. The 4bpp
     * page begins at x=64,y=0; U=0..3 samples VRAM word x=64.
     * CLUT occupies x=0..15,y=40, clear of the displayed 12x9 area. */
    setRECT(&tex_rect, 64, 0, 1, 2);
    setRECT(&clut_rect, 0, 40, 16, 1);
    LoadImage(&tex_rect, (unsigned int *)texels);
    LoadImage(&clut_rect, (unsigned int *)palette);
    ClearOTag(ot, 1);
    /* Dedicated 4bpp CLUT quad below the F4. White-neutral modulation
     * leaves CLUT red/green easy to distinguish from the background. */
    SetPolyFT4(&textured);
    setXYWH(&textured, 4, 5, 4, 2);
    setUVWH(&textured, 0, 0, 4, 2);
    setRGB0(&textured, 128, 128, 128);
    setTPage(&textured, 0, 0, 64, 0);
    setClut(&textured, 0, 40);
    AddPrim(&ot[0], &textured);
    /* Real untextured polygon from the original DrawOTag->FillQuad path.
     * The native 12x9 point (5,2) should be magenta. Center (6,4)
     * remains the animated background, avoiding ambiguous motion tests. */
    SetPolyF4(&polygon);
    setXYWH(&polygon, 4, 1, 4, 3);
    setRGB0(&polygon, 255, 0, 255);
    AddPrim(&ot[0], &polygon);
    tile(&corner[0], 0, 0, 2, 2, 255, 0, 0);
    tile(&corner[1], 10, 0, 2, 2, 0, 255, 0);
    tile(&corner[2], 0, 7, 2, 2, 0, 0, 255);
    tile(&corner[3], 10, 7, 2, 2, 255, 255, 0);
    for (int n = 0; n < 4; ++n) AddPrim(&ot[0], &corner[n]);
    tile(&background, 0, 0, 12, 9, 96, 96, (unsigned char)(frame * 3));
    AddPrim(&ot[0], &background);
    DrawOTag(ot);
}

/* Test-only inert providers for optional game data, localized overlays,
 * HD packs, debug recording and OSD. They never become game implementations.
 * Original library code still rasterizes BGR555 VRAM and walks the OT.
 */
int PC_MovieSubsLoaded(void) { return 0; }
int PC_OverlayIsOpen(void) { return 0; }
int PC_BattleSpeedGet(void) { return 1; }
const char *PC_LangBgDir(void) { return NULL; }
void PC_LangPatchFwdUpload(int x, int y, int w, int h, unsigned short *pix) {
    (void)x; (void)y; (void)w; (void)h; (void)pix;
}
void PC_UpdateCamOsd(void) {}
void TrcInit(void) {}
void TrcWrite(char op, const void *a, u32 na, const void *b, u32 nb) {
    (void)op; (void)a; (void)na; (void)b; (void)nb;
}
void TrcPrim(int type, const void *p) { (void)type; (void)p; }
void TrcFrameEnd(void) {}
int TrcReplaying(void) { return 0; }
void HdPack_OnLoad(const RECT *r, const unsigned short *p) {
    (void)r; (void)p;
}
int HdAnyActive(void) { return 0; }
int HdActive(void) { return 0; }
const char *HdDumpDir(void) { return NULL; }
int HdRegionCount(void) { return 0; }
int HdReplaceCount(void) { return 0; }
HdRegion *HdFindTriRegion(int tp, int umin, int umax, int vmin, int vmax) {
    (void)tp; (void)umin; (void)umax; (void)vmin; (void)vmax;
    return NULL;
}
void HdMaybeDump(int tp, int clut, int umin, int umax, int vmin, int vmax) {
    (void)tp; (void)clut; (void)umin; (void)umax; (void)vmin; (void)vmax;
}

int main(void) {
    VhSwitchSdl2ObserverBackend backend = {0};
    int ok = 0, w = 0, h = 0, scale = 0;
    if (!vh_switch_sdl2_observer_backend_init(
            &backend, "VH original DrawOTag raster probe", 1280, 720)) {
        fprintf(stderr, "Native raster probe: backend initialization failed\n");
        goto done;
    }
    if (!PC_GpuInit(12, 9, "Switch backend owns context")) {
        fprintf(stderr, "Native raster probe: pinned GPU init rejected backend\n");
        goto done;
    }
    PC_GpuGetWindowSize(&w, &h, &scale);
    if (w != 1280 || h != 720 || scale != 1) {
        fprintf(stderr, "Native raster probe: incorrect %dx%d scale %d\n", w, h, scale);
        goto done;
    }
    g_vhInternalScale = 1;
    ResetGraph(0);
    for (int frame = 0; frame < 3600; ++frame) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) goto done;
        }
        draw_frame(frame);
        if (!vh_switch_observer_last_result()) {
            fprintf(stderr, "Native raster probe: DrawOTag frame %d failed\n", frame);
            goto done;
        }
        SDL_Delay(16);
    }
    ok = 1;
done:
    vh_switch_sdl2_observer_backend_shutdown(&backend);
    return ok ? 0 : 1;
}
