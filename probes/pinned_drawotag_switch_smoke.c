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
    POLY_FT4 textured, textured8, textured15, transparent15, semi15;
    SPRT sprite;
    DR_MODE mode;
    /* 4bpp: four texels (1,2,1,2) per packed 16-bit VRAM word. */
    unsigned short texels[2] = {0x2121, 0x2121};
    unsigned short palette[16] = {0, 0x001f, 0x03e0};
    unsigned short texels8[2] = {0x0201, 0x0201};
    unsigned short palette8[256] = {0, 0x7c00, 0x7fff};
    unsigned short texels15[4] = {0x03ff, 0x7c1f, 0x03ff, 0x7c1f};
    unsigned short texels_alpha[4] = {0x0000, 0x7fe0, 0x0000, 0x7fe0};
    unsigned short texels_stp[4] = {0x801f, 0x03e0, 0x801f, 0x03e0};
    RECT tex_rect, clut_rect, tex8_rect, clut8_rect, tex15_rect, alpha_rect, stp_rect;
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
    setRECT(&tex8_rect, 128, 0, 1, 2);
    setRECT(&clut8_rect, 0, 41, 256, 1);
    LoadImage(&tex8_rect, (unsigned int *)texels8);
    LoadImage(&clut8_rect, (unsigned int *)palette8);
    /* 15bpp direct-colour page: no CLUT lookup; two contrasting texels. */
    setRECT(&tex15_rect, 192, 0, 2, 2);
    LoadImage(&tex15_rect, (unsigned int *)texels15);
    setRECT(&alpha_rect, 256, 0, 2, 2);
    LoadImage(&alpha_rect, (unsigned int *)texels_alpha);
    setRECT(&stp_rect, 320, 0, 2, 2);
    LoadImage(&stp_rect, (unsigned int *)texels_stp);
    ClearOTag(ot, 1);
    /* Original textured SPRT path: sprite has NO tpage field. DrawOTag
     * must read its page from DR_MODE in OT order (mode before sprite).
     * Reuse the 4bpp red/green CLUT and keep away from other test quads. */
    SetSprt(&sprite);
    setXY0(&sprite, 0, 3);
    setWH(&sprite, 2, 2);
    setUV0(&sprite, 0, 0);
    setRGB0(&sprite, 128, 128, 128);
    setClut(&sprite, 0, 40);
    AddPrim(&ot[0], &sprite);
    SetDrawMode(&mode, 0, 0, GetTPage(0, 0, 64, 0), NULL);
    AddPrim(&ot[0], &mode);
    /* ABR=0: STP-marked red blends 50/50 with background;
     * unmarked green stays opaque within the same semi-trans FT4. */
    SetPolyFT4(&semi15);
    setXYWH(&semi15, 8, 5, 2, 2);
    setUVWH(&semi15, 0, 0, 2, 2);
    setRGB0(&semi15, 128, 128, 128);
    setTPage(&semi15, 2, 0, 320, 0);
    setClut(&semi15, 0, 0);
    SetSemiTrans(&semi15, 1);
    AddPrim(&ot[0], &semi15);
    /* Zero-valued direct-colour texels must leave the animated TILE
     * background visible; nonzero cyan neighbours must overwrite it. */
    SetPolyFT4(&transparent15);
    setXYWH(&transparent15, 2, 2, 2, 2);
    setUVWH(&transparent15, 0, 0, 2, 2);
    setRGB0(&transparent15, 128, 128, 128);
    setTPage(&transparent15, 2, 0, 256, 0);
    setClut(&transparent15, 0, 0);
    AddPrim(&ot[0], &transparent15);
    SetPolyFT4(&textured15);
    setXYWH(&textured15, 2, 4, 2, 2);
    setUVWH(&textured15, 0, 0, 2, 2);
    setRGB0(&textured15, 128, 128, 128);
    setTPage(&textured15, 2, 0, 192, 0);
    setClut(&textured15, 0, 0); /* ignored for direct-colour texels */
    AddPrim(&ot[0], &textured15);
    /* 8bpp page with its own 256-colour CLUT, safely off-screen. */
    SetPolyFT4(&textured8);
    setXYWH(&textured8, 8, 3, 2, 2);
    setUVWH(&textured8, 0, 0, 2, 2);
    setRGB0(&textured8, 128, 128, 128);
    setTPage(&textured8, 1, 0, 128, 0);
    setClut(&textured8, 0, 41);
    AddPrim(&ot[0], &textured8);
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
