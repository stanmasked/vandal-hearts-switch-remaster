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
    SetDefDrawEnv(&draw, 0, 0, 12, 9);
    SetDefDispEnv(&display, 0, 0, 12, 9);
    PutDrawEnv(&draw);
    PutDispEnv(&display);
    ClearOTag(ot, 1);
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
