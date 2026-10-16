/* Asset-free integration probe for the ORIGINAL pinned PC-port DrawOTag.
 * Uses the genuine ordering-table API + software rasterizer + PC_GpuPresent.
 * Stub hooks below are strictly test-only: no original game loop/assets.
 */
#include <SDL2/SDL.h>
#include <stdio.h>
#include <signal.h>
#include <string.h>
#include "PsyQ/libgpu.h"
#include "PsyQ/libgte.h"
#include "inline_gte.h"
#include "pc_gpu_internal.h"
#include "pc_platform.h"
#include "switch_sdl2_observer_backend.h"
#include "vh_private_map_bank.h"
#include "vh_private_map_geometry.h"
#include "vh_private_map_shading.h"
#include "vh_private_map_light.h"

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
/* Exact original LoadMapTextures data layout (not a TIM file):
 * F_TEXxx.DAT is a 32768-byte raw 4bpp page, LAND_DT map record is
 * 257 UVWH groups + 257 CLUT selectors + 512 palette bytes.
 * These are synthetic values, NOT bytes copied from a retail disc. */
static unsigned short map_tex_words[64 * 256];
static unsigned short map_clut_words[16 * 16];
static VhPrivateMapBank private_map;
static int private_map_active;
static VhPreviewGeometry private_geometry;
static int private_geometry_active;
static unsigned char private_light_intensity=128;
static const unsigned char map_land_record[1797] = {
    [0] = 16, [1] = 16, [2] = 15, [3] = 15,
    [257 * 4] = 32,              /* Slot 0 -> first local CLUT row */
    [257 * 5 + 2] = 0x1f,       /* CLUT[1] = red 0x001f */
    [257 * 5 + 4] = 0xe0,       /* CLUT[2] = green 0x03e0 */
    [257 * 5 + 5] = 0x03
};

static int draw_frame(int frame) {
    DRAWENV draw;
    DISPENV display;
    unsigned int ot[1];
    TILE corner[4], background;
    POLY_F4 polygon;
    POLY_FT4 textured, textured8, textured15, transparent15, semi15;
    POLY_FT4 abr_add, abr_sub, abr_quarter;
    SPRT sprite, window_sprite, v_window_sprite, tim_sprite, map_sprite;
    DR_MODE mode, window_mode, window_reset, v_window_mode, v_window_reset, tim_mode, map_mode;
    RECT window_rect, reset_rect, v_window_rect, v_reset_rect;
    TIM_IMAGE tim_image;
    RECT map_tex_rect = {320, 0, 64, 256};
    RECT map_clut_rect = {672, 496, 16, 16};
    /* One valid 4bpp TIM byte stream (PS1 little-endian word layout),
     * NOT extracted game artwork. CLUT is 16x1 at (0,42); packed
     * image is 2x2 VRAM words at (384,0), 8x2 logical texels.
     * Exercise the ORIGINAL OpenTIM/ReadTIM parser and LoadImage,
     * not just a manually constructed RECT+CLUT fixture. */
    unsigned int tim_words[18] = {
        0x00000010u, 0x00000008u, 0x0000002cu,
        0x002a0000u, 0x00010010u,
        0x001f0000u, 0x000003e0u,
        0, 0, 0, 0, 0, 0,
        0x00000014u, 0x00000180u, 0x00020002u,
        0x21212121u, 0x21212121u
    };
    /* 4bpp: four texels (1,2,1,2) per packed 16-bit VRAM word. */
    unsigned short texels[2] = {0x2121, 0x2121};
    /* Window redirects U=0/1 to U=8/9 (word x=66): blue/white. */
    unsigned short texels_window[2] = {0x0043, 0x0043};
    /* V-window selects rows 8/9: blue/white above magenta/yellow. */
    unsigned short texels_vwindow[2] = {0x0043, 0x0065};
    unsigned short palette[16] = {0, 0x001f, 0x03e0, 0x7c00, 0x7fff, 0x7c1f, 0x03ff};
    unsigned short texels8[2] = {0x0201, 0x0201};
    unsigned short palette8[256] = {0, 0x7c00, 0x7fff};
    unsigned short texels15[4] = {0x03ff, 0x7c1f, 0x03ff, 0x7c1f};
    unsigned short texels_alpha[4] = {0x0000, 0x7fe0, 0x0000, 0x7fe0};
    unsigned short texels_stp[4] = {0x801f, 0x03e0, 0x801f, 0x03e0};
    RECT tex_rect, tex_window_rect, tex_vwindow_rect, clut_rect, tex8_rect, clut8_rect, tex15_rect, alpha_rect, stp_rect;
    SetDefDrawEnv(&draw, 0, 0, 12, 9);
    SetDefDispEnv(&display, 0, 0, 12, 9);
    PutDrawEnv(&draw);
    PutDispEnv(&display);
    /* The original LoadMapTextures path uploads a RAW F_TEX page, then
     * 512 palette bytes from LAND_DT at record offset 1285. The test
     * page's only coloured texels are at U16/17,V16/17 to avoid the
     * existing 15bpp STP test at VRAM x320,y0. */
    if (!private_map_active) {
        map_tex_words[16 * 64 + 4] = 0x2121;
        map_tex_words[17 * 64 + 4] = 0x2121;
        memcpy(map_clut_words, map_land_record + 257 * 5, sizeof(map_clut_words));
        if (map_land_record[257 * 4] != 32 ||
            map_land_record[0] != 16 || map_land_record[1] != 16) {
            fprintf(stderr, "Native map bank: invalid synthetic LAND_DT record\n");
            return 0;
        }
    }
    LoadImage(&map_tex_rect, (unsigned int *)map_tex_words);
    LoadImage(&map_clut_rect, (unsigned int *)map_clut_words);
    /* Upload to off-screen VRAM through the ORIGINAL LoadImage. The 4bpp
     * page begins at x=64,y=0; U=0..3 samples VRAM word x=64.
     * CLUT occupies x=0..15,y=40, clear of the displayed 12x9 area. */
    setRECT(&tex_rect, 64, 0, 1, 2);
    setRECT(&clut_rect, 0, 40, 16, 1);
    LoadImage(&tex_rect, (unsigned int *)texels);
    setRECT(&tex_window_rect, 66, 0, 1, 2);
    LoadImage(&tex_window_rect, (unsigned int *)texels_window);
    setRECT(&tex_vwindow_rect, 64, 8, 1, 2);
    LoadImage(&tex_vwindow_rect, (unsigned int *)texels_vwindow);
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
    OpenTIM(tim_words);
    if (!ReadTIM(&tim_image) || tim_image.mode != 8 ||
        !tim_image.crect || !tim_image.prect ||
        !tim_image.caddr || !tim_image.paddr ||
        tim_image.crect->x != 0 || tim_image.crect->y != 42 ||
        tim_image.crect->w != 16 || tim_image.crect->h != 1 ||
        tim_image.prect->x != 384 || tim_image.prect->y != 0 ||
        tim_image.prect->w != 2 || tim_image.prect->h != 2) {
        fprintf(stderr, "Native DrawOTag TIM parser rejected packaged fixture\n");
        return 0;
    }
    LoadImage(tim_image.crect, tim_image.caddr);
    LoadImage(tim_image.prect, tim_image.paddr);
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
    /* OT traversal is newest first: window_mode -> window_sprite ->
     * window_reset -> mode -> sprite. Reset explicitly before the
     * baseline SPRT, so it still samples original U=0/1 red/green. */
    setRECT(&reset_rect, 0, 0, 256, 256);
    SetDrawMode(&window_reset, 0, 0, GetTPage(0, 0, 64, 0), &reset_rect);
    AddPrim(&ot[0], &window_reset);
    SetSprt(&window_sprite);
    setXY0(&window_sprite, 0, 5);
    setWH(&window_sprite, 2, 2);
    setUV0(&window_sprite, 0, 0);
    setRGB0(&window_sprite, 128, 128, 128);
    setClut(&window_sprite, 0, 40);
    AddPrim(&ot[0], &window_sprite);
    /* GP0(E2h): maskX=(256-248)/8=1, offX=8/8=1;
     * u'=(u & ~8) | 8 -> U0/1 maps to U8/9. */
    setRECT(&window_rect, 8, 0, 248, 256);
    SetDrawMode(&window_mode, 0, 0, GetTPage(0, 0, 64, 0), &window_rect);
    AddPrim(&ot[0], &window_mode);
    /* Second independent E2h test along V. Newest-first OT processing:
     * v_window_mode -> v_window_sprite -> v_window_reset -> window_mode.
     * y'=((y & ~8) | 8) selects the distinct rows 8 and 9 in VRAM. */
    setRECT(&v_reset_rect, 0, 0, 256, 256);
    SetDrawMode(&v_window_reset, 0, 0, GetTPage(0, 0, 64, 0), &v_reset_rect);
    AddPrim(&ot[0], &v_window_reset);
    SetSprt(&v_window_sprite);
    setXY0(&v_window_sprite, 2, 0);
    setWH(&v_window_sprite, 2, 2);
    setUV0(&v_window_sprite, 0, 0);
    setRGB0(&v_window_sprite, 128, 128, 128);
    setClut(&v_window_sprite, 0, 40);
    AddPrim(&ot[0], &v_window_sprite);
    setRECT(&v_window_rect, 0, 8, 256, 248);
    SetDrawMode(&v_window_mode, 0, 0, GetTPage(0, 0, 64, 0), &v_window_rect);
    AddPrim(&ot[0], &v_window_mode);
    /* Original BGR555 semi-trans modes ABR=1,2,3 on the bottom strip.
     * Reuse the STP-marked red / unmarked green texels at VRAM (320,0).
     * Quads x=2..8,y=7..9 avoid the four corner TILE markers and
     * every existing FT4/SPRT probe. With the red background channel
     * quantized to 12/31: add=31, subtract=0, quarter=12+(31>>2)=19.
     * The adjacent unmarked green must remain opaque in every mode. */
    SetPolyFT4(&abr_add);
    setXYWH(&abr_add, 2, 7, 2, 2);
    setUVWH(&abr_add, 0, 0, 2, 2);
    setRGB0(&abr_add, 128, 128, 128);
    setTPage(&abr_add, 2, 1, 320, 0);
    setClut(&abr_add, 0, 0);
    SetSemiTrans(&abr_add, 1);
    AddPrim(&ot[0], &abr_add);
    SetPolyFT4(&abr_sub);
    setXYWH(&abr_sub, 4, 7, 2, 2);
    setUVWH(&abr_sub, 0, 0, 2, 2);
    setRGB0(&abr_sub, 128, 128, 128);
    setTPage(&abr_sub, 2, 2, 320, 0);
    setClut(&abr_sub, 0, 0);
    SetSemiTrans(&abr_sub, 1);
    AddPrim(&ot[0], &abr_sub);
    SetPolyFT4(&abr_quarter);
    setXYWH(&abr_quarter, 6, 7, 2, 2);
    setUVWH(&abr_quarter, 0, 0, 2, 2);
    setRGB0(&abr_quarter, 128, 128, 128);
    setTPage(&abr_quarter, 2, 3, 320, 0);
    setClut(&abr_quarter, 0, 0);
    SetSemiTrans(&abr_quarter, 1);
    AddPrim(&ot[0], &abr_quarter);
    /* Serialized TIM -> original OpenTIM/ReadTIM -> original LoadImage:
     * primitive samples pixel indices 1/2 from VRAM page x=384,
     * looking up the independent CLUT uploaded at VRAM y=42. */
    SetSprt(&tim_sprite);
    setXY0(&tim_sprite, 8, 1);
    setWH(&tim_sprite, 2, 2);
    setUV0(&tim_sprite, 0, 0);
    setRGB0(&tim_sprite, 128, 128, 128);
    setClut(&tim_sprite, 0, 42);
    AddPrim(&ot[0], &tim_sprite);
    SetDrawMode(&tim_mode, 0, 0, GetTPage(0, 0, 384, 0), &reset_rect);
    AddPrim(&ot[0], &tim_mode);
    /* Raw map texture bank -> original LoadImage -> SPRT/DR_MODE.
     * Native x8..10,y7..9 is the last unused 2x2 region. Slot 0
     * UVWH=(16,16,15,15), CLUT ID 32 maps to (672,496). */
    SetSprt(&map_sprite);
    setXY0(&map_sprite, 8, 7);
    setWH(&map_sprite, 2, 2);
    if (private_map_active) {
        setUV0(&map_sprite, private_map.uvwh[0], private_map.uvwh[1]);
        setClut(&map_sprite, 672, 496 + private_map.local_clut_id - 32);
    } else {
        setUV0(&map_sprite, map_land_record[0], map_land_record[1]);
        setClut(&map_sprite, 672, 496);
    }
    setRGB0(&map_sprite, 128, 128, 128);
    AddPrim(&ot[0], &map_sprite);
    SetDrawMode(&map_mode, 0, 0, GetTPage(0, 0, 320, 0), &reset_rect);
    AddPrim(&ot[0], &map_mode);
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
    return 1;
}

/* PRIVATE preview, only reachable if BOTH user-owned asset files have been
 * validated and loaded from SD. Draws the source-authored map #11 GFX slot
 * 241 UVWH and local CLUT as one POLY_FT4 through the original DrawOTag.
 * It is NOT the original map geometry or game camera. The public CI
 * cannot enter this branch because no proprietary files are supplied. */
static int draw_private_map_preview(void) {
    DRAWENV draw;
    DISPENV display;
    enum { PRIVATE_OT_BUCKETS = 256 };
    unsigned int ot[PRIVATE_OT_BUCKETS];
    TILE clear;
    POLY_FT4 preview, terrain_faces[VH_MAP_MODEL_MAX_FACES];
    unsigned face_index, face_drawn = 0;
    RECT page = {320, 0, 64, 256};
    RECT palette = {672, 496, 16, 16};
    if (!private_map_active) return 0;
    SetDefDrawEnv(&draw, 0, 0, 12, 9);
    SetDefDispEnv(&display, 0, 0, 12, 9);
    PutDrawEnv(&draw);
    PutDispEnv(&display);
    LoadImage(&page, (unsigned int *)map_tex_words);
    LoadImage(&palette, (unsigned int *)map_clut_words);
    ClearOTag(ot, PRIVATE_OT_BUCKETS);
    if (private_geometry_active) {
        MATRIX camera = {0};
        SVECTOR light_rotation = {0,0,0,0};
        CVECTOR light_base = {128,128,128,0};
        SVECTOR light_normals[VH_MAP_SIDE_NORMALS];
        CVECTOR face_lights[VH_MAP_SIDE_NORMALS];
        SVECTOR pitch = {-512, 0, 0, 0};
        VECTOR camera_zoom = {0, 0, 96, 0};
        /* The pinned ORIGINAL PC-port libgte.c models PS1 RTPT,
         * RTPS, perspective division and depth quantization. This
         * neutral test camera is selected solely for our 12x9 probe,
         * NOT copied from the game's battle camera state. */
        InitGeom();
        vh_map_init_side_normals(light_normals);
        vh_map_update_light(face_lights, light_normals,
                            &light_rotation, &light_base,
                            private_light_intensity, 11);
        SetGeomOffset(6, 4);
        SetGeomScreen(14);
        RotMatrix(&pitch, &camera);
        TransMatrix(&camera, &camera_zoom);
        SetRotMatrix(&camera);
        SetTransMatrix(&camera);
        /* Original RenderMapTile GTE sequence and depth-bucket submission
         * with per-face authored UVWH and CLUT. The camera constants
         * remain TEST ONLY (not recovered from actual game data). */
        for (face_index = 0; face_index < private_geometry.face_count;
             ++face_index) {
            const VhPreviewFace *face = &private_geometry.faces[face_index];
            unsigned slot, palette_id;
            const unsigned char *uv;
            SVECTOR source_vertices[4];
            int opz, otz;
            unsigned i;
            POLY_FT4 *poly;
            if (face->local_gfx <= 0) continue;
            slot = (unsigned)face->local_gfx;
            if (slot >= VH_MAP_SLOTS) continue; /* another texture page */
            uv = private_map.slot_uvwh[slot];
            palette_id = private_map.slot_clut_ids[slot];
            if (palette_id < 32u || palette_id > 47u ||
                uv[2] < 1 || uv[3] < 1 ||
                (unsigned)uv[0] + uv[2] >= 256u ||
                (unsigned)uv[1] + uv[3] >= 256u)
                return 0;
            for (i = 0; i < 4; ++i) {
                source_vertices[i].vx = face->vertex[i][0];
                source_vertices[i].vy = face->vertex[i][1];
                source_vertices[i].vz = face->vertex[i][2];
                source_vertices[i].pad = 0;
            }
            /* This is the actual upstream RenderMapTile GTE opcode
             * sequence, including signed backface rejection:
             * RTPT -> NCLIP -> RTPS -> AVSZ4. Unlike RotTransPers4,
             * NCLIP must execute BEFORE loading the fourth vertex,
             * while SXY FIFO still contains source vertices 0/1/2. */
            gte_ldv3(&source_vertices[0], &source_vertices[1],
                     &source_vertices[2]);
            gte_rtpt();
            gte_nclip();
            gte_stopz(&opz);
            if (opz <= 0) continue;
            poly = &terrain_faces[face_drawn++];
            SetPolyFT4(poly);
            gte_stsxy3(&poly->x0, &poly->x1, &poly->x3);
            gte_ldv0(&source_vertices[3]);
            gte_rtps();
            gte_stsxy(&poly->x2);
            gte_avsz4();
            gte_stotz(&otz);
            if (otz < 5) otz = 5; /* RenderMapTile near OT clamp */
            if (otz >= PRIVATE_OT_BUCKETS) otz = PRIVATE_OT_BUCKETS - 1;
            setUVWH(poly, uv[0], uv[1], uv[2], uv[3]);
            /* Per-face shade selector comes from the original
             * MapTileModel. The color table was computed with the
             * original pinned GTE NCCS UpdateLight pipeline.
             * Intensity 128 is a neutral, regression-compatible default;
             * intensity 32 is explicitly selected by the isolated
             * LIGHT_TEST_INTENSITY.BIN synthetic SD fixture. */
            if (face->shade_index >= VH_MAP_SIDE_NORMALS) return 0;
            {
                const CVECTOR *side = &face_lights[face->shade_index];
                setRGB0(poly,
                    vh_map_distance_component(side->r, otz),
                    vh_map_distance_component(side->g, otz),
                    vh_map_distance_component(side->b, otz));
            }
            setTPage(poly, 0, 0, 320, 0);
            setClut(poly, 672, 496 + palette_id - 32);
            AddPrim(&ot[PRIVATE_OT_BUCKETS - otz], poly);
        }
        if (!face_drawn) return 0;
    } else {
        /* Previously accepted single authored-texture patch baseline. */
        SetPolyFT4(&preview);
        setXYWH(&preview, 1, 1, 10, 7);
        setUVWH(&preview,
                private_map.uvwh[0], private_map.uvwh[1],
                private_map.uvwh[2], private_map.uvwh[3]);
        setRGB0(&preview, 128, 128, 128);
        setTPage(&preview, 0, 0, 320, 0);
        setClut(&preview, 672, 496 + private_map.local_clut_id - 32);
        AddPrim(&ot[1], &preview);
    }
    tile(&clear, 0, 0, 12, 9, 0, 0, 0);
    /* OT bucket zero draws first; farther faces (larger OTZ) are
     * inserted in earlier buckets, nearer faces over them. */
    AddPrim(&ot[0], &clear);
    DrawOTag(ot);
    return 1;
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
    /* Optional private Switch SD files: both absent => previous asset-free
     * CI path; any partial/invalid pair => abort without silent fallback.
     * Actual retail files are NEVER embedded in this source or NRO. */
    {
        int asset_status = vh_private_map_bank_load_pair(
            VH_PRIVATE_MAP_TEXTURE_PATH, VH_PRIVATE_MAP_LAND_PATH,
            11, 241, &private_map);
        if (asset_status < 0) {
            fprintf(stderr,
                    "Private map 11 files invalid or incomplete; refusing to draw\n");
            goto done;
        }
        if (asset_status == 1) {
            memcpy(map_tex_words, private_map.texture, sizeof(map_tex_words));
            memcpy(map_clut_words, private_map.palette, sizeof(map_clut_words));
            private_map_active = 1;
            fprintf(stderr,
                    "Private map 11 F_TEX/LAND_DT loaded; slot 241 CLUT %u "
                    "UV=(%u,%u)\n",
                    (unsigned)private_map.local_clut_id,
                    (unsigned)private_map.uvwh[0],
                    (unsigned)private_map.uvwh[1]);
            {
                int geometry_status = vh_private_map_geometry_load(
                    VH_MAP_GEOMETRY_PATH, 6, 3, &private_geometry);
                if (geometry_status < 0) {
                    fprintf(stderr,
                            "Private map11 geometry file malformed; refusing to draw\n");
                    goto done;
                }
                private_geometry_active = geometry_status == 1;
                if (private_geometry_active) {
                    int light_status = vh_map_read_demo_intensity(
                        VH_MAP_LIGHT_DEMO_PATH, &private_light_intensity);
                    if (light_status < 0) {
                        fprintf(stderr, "Private light intensity file invalid\\n");
                        goto done;
                    }
                }
            }
        }
    }
    ResetGraph(0);
    for (int frame = 0; frame < 3600; ++frame) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) goto done;
        }
        if (!(private_map_active ? draw_private_map_preview() : draw_frame(frame))) {
            fprintf(stderr, "Native raster probe: original DrawOTag frame %d failed\n", frame);
            goto done;
        }
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
