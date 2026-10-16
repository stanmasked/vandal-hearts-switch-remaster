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
#include "vh_map02_hd_lookup_v24.h"

/* Actual original game decompressor, built from src/maps/unpack.c. */
extern void ProcessMapFileData(u8 *input);
extern s32 UnpackMapFileData(u8 *input, u8 *output, s32 compressed_len);

/* Production graphics globals supplied by generated game data in real builds.
 * V43 defines only the ones consumed by RenderMapTile and its v39 hook. */
static Graphics s_v43Graphics;
Graphics *gGraphicsPtr = &s_v43Graphics;
s32 gQuadIndex;
CVECTOR gSideLightColor[26];
u8 gShowBlueMovementGrid;
u8 gGridColorOscillation;
s16 gGfxClutIds[GFX_CT];
s16 gGfxTPageIds[GFX_CT];
u8 gGfxSubTextures[GFX_CT][4];
State gState;
MapTileModel *gMapRowPointers[28];
static MapTileModel s_fixture[12][28];
static struct { MapTileModel tiles[12][28]; unsigned char guard[64]; } s_decoded;
u8 *gMapDataPtr = (u8 *)s_decoded.tiles;
static const VH_Map02Texture *s_slot241, *s_slot243;

static unsigned short s_cell[16 * 4];
static unsigned short s_clut_red[16], s_clut_green[16];
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
    MapTileModel *t = &s_fixture[8][19];
    int i;
    memset(s_fixture, 0, sizeof(s_fixture));
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
    s_fixture[11][11] = *t;
    s_fixture[11][11].gfx[0] = 643; /* fixed second original-layout face: v24 slot 243 */
    /* Use REAL v24 lookup rows from user-owned M_MAP02 manifest. */
    V43_CHECK(VH_MAP02_HD_SLOT_COUNT == 120, "full 120-slot v24 lookup");
    s_slot241 = VH_Map02Find(5, 31978, 240, 192);
    s_slot243 = VH_Map02Find(5, 31850, 240, 208);
    V43_CHECK(s_slot241 && s_slot241->slot == 241 &&
              s_slot241->canonical == 241, "exact v24 slot 241 identity");
    V43_CHECK(s_slot243 && s_slot243->slot == 243 &&
              s_slot243->canonical == 243, "exact v24 slot 243 identity");
    if (!s_slot241 || !s_slot243) return;
    for (i = 641; i <= 644; ++i) {
        const VH_Map02Texture *entry;
        if (i == 642) continue; /* local slot 242 is absent from the real v24 table */
        entry = i == 643 ? s_slot243 : s_slot241;
        V43_CHECK(entry->slot == i - 400 || i == 644,
                  "gfx global-to-local slot offset matches v24");
        gGfxClutIds[i] = entry->clut;
        gGfxTPageIds[i] = entry->tpage;
        gGfxSubTextures[i][0] = entry->u;
        gGfxSubTextures[i][1] = entry->v;
        gGfxSubTextures[i][2] = entry->w - 1;
        gGfxSubTextures[i][3] = entry->h - 1;
    }
    {
        int mx = -1, my = -1;
        V43_CHECK(VH_Map02ToMaster(s_slot241, 4, 0, 0, &mx, &my)
                  && mx == 0 && my == 0, "v24 canonical HD coordinate identity");
        V43_CHECK(VH_Map02Find(5, 31850, 240, 208) == s_slot243,
                  "v24 CLUT selects the protected slot 243");
        V43_CHECK(VH_Map02Find(5, 31978, 240, 208) == 0,
                  "v24 wrong palette cannot identify protected slot");
    }
    gSideLightColor[0].r = 128;
    gSideLightColor[0].g = 128;
    gSideLightColor[0].b = 128;
    InitGeom(); /* REAL PC GTE, no projected vertices precomputed. */
    SetGeomOffset(96, 96);
    SetGeomScreen(1000);
}


/* Encode a whole synthetic 28*12-tile PRS payload as eight literal bytes per
 * flag byte. The actual game unpacker, not a test decoder, must reconstruct
 * the exact MapTileModel layout in gMapDataPtr. Bounds and guards are
 * validated independently because production unpack.c assumes trusted disc.
 */
static void load_synthetic_map_via_real_unpack(void) {
    const unsigned char *src = (const unsigned char *)s_fixture;
    const size_t n = sizeof(s_fixture);
    const size_t groups = (n + 7) / 8;
    const size_t cap = 4 + n + groups + 16;
    unsigned char *compressed = (unsigned char *)calloc(cap, 1);
    unsigned char *p;
    size_t offset = 0, remain = n;
    int z;
    if (!compressed) { fprintf(stderr, "[v44] OOM\n"); exit(2); }
    p = compressed + 4;
    while (remain) {
        size_t chunk = remain > 8 ? 8 : remain;
        *p++ = 0; /* 8 literal decisions, matching game's 0xff00 modeBits */
        memcpy(p, src + offset, chunk);
        p += chunk;
        remain -= chunk;
        offset += chunk;
    }
    {
        const size_t length = (size_t)(p - (compressed + 4));
        int i;
        unsigned char probe[sizeof(s_fixture) + 64];
        memset(probe, 0xa5, sizeof(probe));
        V43_CHECK(length < 0x7fffffff, "PRS synthetic compressed length fits s32");
        V43_CHECK(UnpackMapFileData(compressed+4, probe, (s32)length) == (s32)n,
                  "original UnpackMapFileData output has exact expected size");
        V43_CHECK(memcmp(probe, s_fixture, n) == 0, "original unpack reproduces all 28x12 tiles");
        for (i = 0; i < 64; ++i)
            V43_CHECK(probe[n+i] == 0xa5, "raw decompressor never exceeds tile buffer");
        compressed[0] = (unsigned char)(length & 0xff);
        compressed[1] = (unsigned char)((length >> 8) & 0xff);
        compressed[2] = (unsigned char)((length >> 16) & 0xff);
        compressed[3] = (unsigned char)((length >> 24) & 0xff);
    }
    memset(&s_decoded, 0, sizeof(s_decoded));
    memset(s_decoded.guard, 0x5a, sizeof(s_decoded.guard));
    ProcessMapFileData(compressed);
    V43_CHECK(memcmp(s_decoded.tiles, s_fixture, n) == 0,
              "original ProcessMapFileData reconstructed full layout at gMapDataPtr");
    for (z = 0; z < (int)sizeof(s_decoded.guard); ++z)
        V43_CHECK(s_decoded.guard[z] == 0x5a,
                  "ProcessMapFileData preserved map buffer guard");
    for (z = 0; z < 12; ++z) gMapRowPointers[z] = s_decoded.tiles[z];
    V43_CHECK(gMapRowPointers[8][19].faceCt == 1
              && gMapRowPointers[8][19].gfx[0] == 641
              && gMapRowPointers[11][11].faceCt == 1
              && gMapRowPointers[11][11].gfx[0] == 643,
              "28x12 row pointer and face model survive original PRS unpack");
    {
        const char *fixture_output = getenv("VH_V45_SYNTHETIC_PRS_OUTPUT");
        if (fixture_output && *fixture_output) {
            FILE *output = fopen(fixture_output, "wb");
            size_t compressed_bytes = (size_t)(p - compressed);
            if (!output || fwrite(compressed, 1, compressed_bytes, output) != compressed_bytes ||
                fclose(output)) {
                fprintf(stderr, "[v45] cannot write synthetic PRS test fixture\n");
                exit(2);
            }
            fprintf(stderr, "[v45] GENERATED_SYNTHETIC_PRS bytes=%lu\n",
                    (unsigned long)compressed_bytes);
        }
    }
    fprintf(stderr, "[v45] REFERENCE_DECODED_FNV64=%016llx\n", v43_hash(s_fixture, n));
    fprintf(stderr, "[v44] UNPACK_OK bytes=%lu compressed=%lu tiles=336 width=28 height=12\n",
            (unsigned long)n, (unsigned long)(p-compressed-4));
    free(compressed);
}

static void make_spoof(POLY_FT4 *q, int gfx) {
    const VH_Map02Texture *entry = gfx == 643 ? s_slot243 : s_slot241;
    SetPolyFT4(q);
    setRGB0(q, 128, 128, 128);
    setXYWH(q, 192, 64, 64, 64);
    q->tpage = entry->tpage;
    q->clut = entry->clut;
    setUVWH(q, entry->u, entry->v, entry->w - 1, entry->h - 1);
}

static void draw_one_frame(int frame, int mapnum, int z, int x, int gfx) {
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
    V43_CHECK(gMapRowPointers[z][x].gfx[0] == gfx,
              "decompressed PRS tile and intended game GFX match BEFORE rendering");
    ClearOTag(ot, OT_SIZE);
    for (i = 0; i < 64; ++i) {
        SetTile(&fillers[i]);
        setRGB0(&fillers[i], 0, 0, 0);
        setXY0(&fillers[i], 280 + (i % 8), 180 + (i / 8));
        setWH(&fillers[i], 1, 1);
        AddPrim(&ot[0], &fillers[i]);
    }
    make_spoof(&sprite, gfx);
    AddPrim(&ot[0], &sprite);
    /* This call produces its own projected POLY_FT4 from SVECTOR vertices,
       calculates GTE back-face and OT depth, then calls the real AddPrim. */
    RenderMapTile(ot, &gMapRowPointers[z][x], GRID_COLOR_NONE);
    V43_CHECK(gQuadIndex == 1, "real RenderMapTile submitted exactly one FT4");
    V43_CHECK(s_v43Graphics.quads[0].tpage == 5,
              "game code resolved synthetic GFX to original texture page");
    {
        const VH_Map02Texture *match = VH_Map02Find(
            s_v43Graphics.quads[0].tpage,
            s_v43Graphics.quads[0].clut,
            s_v43Graphics.quads[0].u0,
            s_v43Graphics.quads[0].v0);
        const VH_Map02Texture *expected = gfx == 643 ? s_slot243 : s_slot241;
        V43_CHECK(match == expected, "game-generated FT4 maps to exact v24 slot");
        V43_CHECK(s_v43Graphics.quads[0].u1 == expected->u + expected->w - 1
                  && s_v43Graphics.quads[0].v2 == expected->v + expected->h - 1,
                  "game-generated corner UVs stay within v24 original slot");
    }
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
    /* Synthetic 4bpp texel index 1 and synthetic PS1 CLUT palettes;
       coordinates (tpage5, u=240, v=192/208) come from true v24 rows. */
    for (i = 0; i < 16 * 4; ++i) s_cell[i] = 0x1111;
    s_clut_red[1] = 0x001f;
    s_clut_green[1] = 0x03e0;
    setRECT(&tex, 320 + 240/4, 192, 4, 16);
    LoadImage(&tex, (unsigned int *)s_cell);
    setRECT(&tex, 320 + 240/4, 208, 4, 16);
    LoadImage(&tex, (unsigned int *)s_cell);
    setRECT(&tex, (31978 & 63) * 16, 31978 >> 6, 16, 1);
    LoadImage(&tex, (unsigned int *)s_clut_red);
    setRECT(&tex, (31850 & 63) * 16, 31850 >> 6, 16, 1);
    LoadImage(&tex, (unsigned int *)s_clut_green);

    setup_model();
    /* Real production PRS decompressor loads a synthetic 28x12 tile grid. */
    load_synthetic_map_via_real_unpack();
    draw_one_frame(1, 11, 8, 19, 641);
    draw_one_frame(2, 11, 11, 11, 643);
    draw_one_frame(3, 2, 8, 19, 641);  /* wrong map: still draws, not tagged */

    if (s_failures) {
        fprintf(stderr, "[v43] FAIL: %d assertions\n", s_failures);
        return 1;
    }
    native = PC_GpuVramBytes(&n_native);
    hires = PC_GpuHiresBytes(&n_hires);
    V43_CHECK(native && hires && n_native && n_hires, "GPU framebuffers readable");
    if (s_failures) return 1;
    fprintf(stderr, "[v44] FRAMEBUFFER_HASH native=%016llx hires=%016llx\n",
            v43_hash(native, n_native), v43_hash(hires, n_hires));
    fprintf(stderr, "[v45] PASS real UnpackMapFileData → bounded preflight fixture → MapTileModel 28x12 → RenderMapTile → libgte.c → "
                    "libgpu.c DrawOTag → pc_raster.c DDA; three SYNTHETIC frames\n");
    return 0;
}
