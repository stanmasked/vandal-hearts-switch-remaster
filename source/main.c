#include <switch.h>
#include <string.h>

#include "game_rules.h"
#include "game_state.h"
#include "map02_battle_fixture.h"
#include "map02_battle8.h"
#include "map02_roster8_smoke_data.h"
#include "game_renderer.h"
#include "platform_input.h"
#include "software_renderer.h"
#include "ft4_textured_quad.h"
#include "ps1_indexed_texture.h"
#include "ps1_abr_blend.h"
#include "map02_terrain_lighting.h"
#include "map02_face_direction.h"

#define FB_WIDTH 1280
#define FB_HEIGHT 720
#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define MOVE_RANGE 2
#define CELL_SIZE 72
#define GRID_X 352
#define GRID_Y 100

#define COLOR_BG       RGBA8_MAXALPHA(12, 18, 34)
#define COLOR_PANEL    RGBA8_MAXALPHA(24, 34, 54)
#define COLOR_GRID     RGBA8_MAXALPHA(58, 74, 96)
#define COLOR_TILE     RGBA8_MAXALPHA(34, 48, 68)
#define COLOR_TILE_ALT RGBA8_MAXALPHA(39, 54, 75)
#define COLOR_RANGE    RGBA8_MAXALPHA(43, 91, 91)
#define COLOR_HERO     RGBA8_MAXALPHA(86, 190, 244)
#define COLOR_ENEMY    RGBA8_MAXALPHA(235, 89, 98)
#define COLOR_CURSOR   RGBA8_MAXALPHA(255, 219, 102)
#define COLOR_WHITE    RGBA8_MAXALPHA(224, 234, 246)
#define COLOR_MUTED    RGBA8_MAXALPHA(105, 126, 151)

/* Synthetic MAP02-like 4bpp atlas and two independent 16-color CLUTs.
 * No proprietary game art is compiled into the Switch prototype. */
static u8 g_ft4_probe_atlas[256 * 128];
static u8 g_ft4_probe_cluts[2][32];
static u32 g_ft4_probe_pixels[2][16 * 16];
static u32 g_ft4_shaded_pixels[2][16 * 16];
static u8 g_ft4_probe_classes[2][16 * 16];
static u8 g_ft4_probe_side_indices[2];
static int g_ft4_probe_ready = 0;

static void fill_rect(u32 *pixels, u32 stride, int x, int y,
                      int width, int height, u32 color) {
    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    vh_canvas_fill_rect(&canvas, x, y, width, height, color);
}

/* Tiny generated 5x7 font: no copyrighted game fonts or external assets. */
static const u8 FONT_5X7[36][5] = {
    {0x7E,0x11,0x11,0x11,0x7E}, {0x7F,0x49,0x49,0x49,0x36},
    {0x3E,0x41,0x41,0x41,0x22}, {0x7F,0x41,0x41,0x22,0x1C},
    {0x7F,0x49,0x49,0x49,0x41}, {0x7F,0x09,0x09,0x09,0x01},
    {0x3E,0x41,0x49,0x49,0x7A}, {0x7F,0x08,0x08,0x08,0x7F},
    {0x00,0x41,0x7F,0x41,0x00}, {0x20,0x40,0x41,0x3F,0x01},
    {0x7F,0x08,0x14,0x22,0x41}, {0x7F,0x40,0x40,0x40,0x40},
    {0x7F,0x02,0x0C,0x02,0x7F}, {0x7F,0x04,0x08,0x10,0x7F},
    {0x3E,0x41,0x41,0x41,0x3E}, {0x7F,0x09,0x09,0x09,0x06},
    {0x3E,0x41,0x51,0x21,0x5E}, {0x7F,0x09,0x19,0x29,0x46},
    {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7F,0x01,0x01},
    {0x3F,0x40,0x40,0x40,0x3F}, {0x1F,0x20,0x40,0x20,0x1F},
    {0x3F,0x40,0x38,0x40,0x3F}, {0x63,0x14,0x08,0x14,0x63},
    {0x07,0x08,0x70,0x08,0x07}, {0x61,0x51,0x49,0x45,0x43},
    {0x3E,0x45,0x49,0x51,0x3E}, {0x00,0x42,0x7F,0x40,0x00},
    {0x62,0x51,0x49,0x49,0x46}, {0x22,0x41,0x49,0x49,0x36},
    {0x18,0x14,0x12,0x7F,0x10}, {0x2F,0x49,0x49,0x49,0x31},
    {0x3E,0x49,0x49,0x49,0x32}, {0x01,0x71,0x09,0x05,0x03},
    {0x36,0x49,0x49,0x49,0x36}, {0x26,0x49,0x49,0x49,0x3E}
};

static const u8 *font_glyph(char ch) {
    static const u8 blank[5] = {0,0,0,0,0};
    static const u8 dash[5] = {0,0,0x08,0,0};
    static const u8 plus[5] = {0x08,0x08,0x3E,0x08,0x08};
    if (ch >= 'A' && ch <= 'Z') return FONT_5X7[ch - 'A'];
    if (ch >= '0' && ch <= '9') return FONT_5X7[26 + ch - '0'];
    if (ch == '-') return dash;
    if (ch == '+') return plus;
    return blank;
}

static void draw_text(u32 *pixels, u32 stride, int x, int y,
                      const char *text, u32 color, int scale) {
    for (const char *p = text; *p; p++) {
        if (*p == ' ') {
            x += 6 * scale;
            continue;
        }
        const u8 *glyph = font_glyph(*p);
        for (int col = 0; col < 5; col++) {
            for (int row = 0; row < 7; row++) {
                if (glyph[col] & (1u << row)) {
                    fill_rect(pixels, stride, x + col * scale, y + row * scale,
                              scale, scale, color);
                }
            }
        }
        x += 6 * scale;
    }
}

/* Synthetic indexed/CLUT -> RGBA32 -> FT4 proof on the real NRO framebuffer.
 * Two MAP02 UV rectangles, (240,192) and (240,208), are represented with
 * generated non-symmetric color patterns. No original game pixels. */
static u32 vh_switch_pack_ps1_rgb(u8 r, u8 g, u8 b, void *unused) {
    (void)unused;
    return RGBA8_MAXALPHA(r, g, b);
}

static void init_ft4_probe_texture(void) {
    const int crop_v[2] = {192, 208};
    memset(g_ft4_probe_atlas, 0, sizeof(g_ft4_probe_atlas));
    memset(g_ft4_probe_cluts, 0, sizeof(g_ft4_probe_cluts));
    g_ft4_probe_ready = 0;
    for (int texture = 0; texture < 2; ++texture) {
        for (int index = 0; index < 16; ++index) {
            /* BGR555; STP on index 3 is preserved by the decoder stats. */
            const u16 raw = index == 0 ? 0 : (u16)(
                ((index * (texture ? 2 : 1)) & 31) |
                (((index * (texture ? 1 : 2)) & 31) << 5) |
                (((15 - index) & 31) << 10) |
                (index == 3 ? 0x8000 : 0));
            g_ft4_probe_cluts[texture][index * 2] = (u8)raw;
            g_ft4_probe_cluts[texture][index * 2 + 1] = (u8)(raw >> 8);
        }
        for (int y = 0; y < 16; ++y) {
            for (int x = 0; x < 16; ++x) {
                const int u = 240 + x;
                const int offset = (crop_v[texture] + y) * 128 + u / 2;
                const u8 index = (u8)((x + (texture ? 5 : 3) * y) & 15);
                if (u & 1) {
                    g_ft4_probe_atlas[offset] =
                        (u8)((g_ft4_probe_atlas[offset] & 0x0f) | (index << 4));
                } else {
                    g_ft4_probe_atlas[offset] =
                        (u8)((g_ft4_probe_atlas[offset] & 0xf0) | index);
                }
            }
        }
        VhPs1Clut4Stats stats = {0, 0, 0};
        if (!vh_ps1_decode_clut4_crop_classified(
                g_ft4_probe_atlas, sizeof(g_ft4_probe_atlas),
                256, 256, 128, g_ft4_probe_cluts[texture], 32,
                240, (size_t)crop_v[texture], 16, 16,
                g_ft4_probe_pixels[texture], 16,
                g_ft4_probe_classes[texture], 16,
                vh_switch_pack_ps1_rgb, NULL, &stats) ||
            stats.pixels_decoded != 256 || stats.transparent_zero_pixels != 16 ||
            stats.stp_flag_pixels != 16) {
            return;
        }
    }
    /* Two synthetic MapTileModel records: +Y top and +X side face.
     * Geometry is generated at startup, not loaded from the PS1 disc. */
    for (int texture = 0; texture < 2; ++texture) {
        u8 tile[304] = {0};
        tile[212] = 0; tile[213] = 1; tile[214] = 2; tile[215] = 3;
        tile[302] = 1;
        if (texture == 0) {
            tile[8 + 4] = 100;  /* vertex1=(0,0,100) */
            tile[16] = 100;     /* vertex2=(100,0,0), +Y normal */
        } else {
            tile[8 + 2] = 100;  /* vertex1=(0,100,0) */
            tile[16 + 4] = 100; /* vertex2=(0,0,100), +X normal */
        }
        if (!vh_map02_face_direction(tile, sizeof(tile), 0,
                                     &g_ft4_probe_side_indices[texture], NULL))
            return;
    }
    g_ft4_probe_ready = 1;
}

/* Explicit visual debugging of STP: magenta means "semi flag detected".
 * This is NOT a PlayStation ABR blend mode and cannot be mistaken for one. */
static void vh_switch_unpack_ps1_rgb(
    u32 pixel, u8 *red, u8 *green, u8 *blue, void *unused) {
    (void)unused;
    *red = (u8)pixel;
    *green = (u8)(pixel >> 8);
    *blue = (u8)(pixel >> 16);
}

/* Cycles the PS1 ABR modes independently of the tactical prototype.
 * This is a synthetic 5-bit reference demonstration, not original art. */
static void draw_ft4_probe(VhCanvas *canvas, u32 *pixels, u32 stride,
                           u32 frame_tick) {
    const VhFt4Point normal[4] = {
        {978, 164}, {1106, 164}, {1106, 292}, {978, 292}
    };
    const VhFt4Point mirror[4] = {
        {1106, 352}, {978, 352}, {978, 480}, {1106, 480}
    };
    VhFt4Vertex quad[4];
    const unsigned mode = (frame_tick / 120u) & 3u;
    const int simulated_otz = 150 + (int)((frame_tick / 4u) % 257u);
    VhMap02LightRgb directional_colors[26] = {{0, 0, 0}};
    directional_colors[0] = (VhMap02LightRgb){128, 128, 128};
    directional_colors[2] = (VhMap02LightRgb){160, 120, 100};
    /* This effect quad uses GPU code 0x2e (ABE), unlike normal MAP02
     * terrain which uses 0x2c and should remain opaque even with STP. */
    const u8 effect_gpu_code = 0x2eu;
    const u16 effect_tpage = (u16)(mode << 5);
    VhPs1AbrState abr = {
        (u8)vh_ps1_tpage_abr(effect_tpage),
        (u8)vh_ps1_ft4_primitive_semi(effect_gpu_code),
        vh_switch_unpack_ps1_rgb, vh_switch_pack_ps1_rgb, NULL
    };
    char mode_label[] = "ABR MODE 0";
    mode_label[9] = (char)('0' + mode);
    draw_text(pixels, stride, 975, 137, "MAP02 LIGHT", COLOR_MUTED, 1);
    draw_text(pixels, stride, 975, 323, mode_label, COLOR_MUTED, 1);
    if (!g_ft4_probe_ready) {
        draw_text(pixels, stride, 975, 500, "CLUT ERROR", COLOR_ENEMY, 1);
        return;
    }
    /* Source-local shading demo: caller supplies face side color, while
     * a synthetic depth cycles through the upstream otz fade curve.
     * No original GTE light table, projection or MAP02 asset is loaded. */
    for (int texture = 0; texture < 2; ++texture) {
        VhMap02LightRgb light;
        if (!vh_map02_select_side_light(
                directional_colors, 26, g_ft4_probe_side_indices[texture],
                simulated_otz, &light)) return;
        if (!vh_map02_tint_crop_rgba32(
                g_ft4_probe_pixels[texture], 16,
                g_ft4_shaded_pixels[texture], 16, 16, 16,
                light, vh_switch_unpack_ps1_rgb,
                vh_switch_pack_ps1_rgb, NULL)) return;
    }
    if (vh_ft4_from_face_perimeter(normal, 0, 0, 15, 15, quad)) {
        (void)vh_canvas_draw_ft4_classified_rgba32(
            canvas, g_ft4_shaded_pixels[0], 16, 16, 16, quad,
            g_ft4_probe_classes[0], 16, NULL, NULL);
    }
    vh_canvas_draw_rect_outline(canvas, 978, 164, 128, 128, COLOR_GRID);
    fill_rect(pixels, stride, 978, 352, 128, 128, COLOR_TILE_ALT);
    if (vh_ft4_from_face_perimeter(mirror, 0, 0, 15, 15, quad)) {
        (void)vh_canvas_draw_ft4_classified_rgba32(
            canvas, g_ft4_shaded_pixels[1], 16, 16, 16, quad,
            g_ft4_probe_classes[1], 16, vh_ps1_abr_stp_blend, &abr);
    }
    vh_canvas_draw_rect_outline(canvas, 978, 352, 128, 128, COLOR_GRID);
}

static void draw_frame(u32 *pixels, u32 stride, int cursor_x, int cursor_y,
                       int hero_x, int hero_y, int enemy_x, int enemy_y,
                       int hero_selected, u32 frame_tick) {
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);

    /* Compact bitmap labels keep the prototype self-contained and asset-free. */
    draw_text(pixels, stride, 72, 28, "VANDAL HEARTS", COLOR_WHITE, 3);
    draw_text(pixels, stride, 72, 59, "TACTICAL PROTOTYPE", COLOR_MUTED, 1);
    draw_text(pixels, stride, 700, 59,
              hero_selected ? "CHOOSE DESTINATION" : "SELECT HERO",
              COLOR_WHITE, 1);
    fill_rect(pixels, stride, 72, 82, FB_WIDTH - 144, 2, COLOR_HERO);

    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    for (int y = 0; y < GRID_HEIGHT; y++) {
        for (int x = 0; x < GRID_WIDTH; x++) {
            const int px = GRID_X + x * CELL_SIZE;
            const int py = GRID_Y + y * CELL_SIZE;
            u32 tile = ((x + y) & 1) ? COLOR_TILE_ALT : COLOR_TILE;

            if (hero_selected &&
                vh_manhattan_distance(hero_x, hero_y, x, y) <= MOVE_RANGE &&
                !(x == enemy_x && y == enemy_y)) {
                tile = COLOR_RANGE;
            }

            VhTilePalette palette = {tile, COLOR_GRID};
            vh_render_grid_tile(&canvas, px, py, CELL_SIZE, palette);

            if (x == hero_x && y == hero_y) {
                const int inset = hero_selected ? 13 : 18;
                fill_rect(pixels, stride, px + inset, py + inset, CELL_SIZE - inset * 2,
                          CELL_SIZE - inset * 2, COLOR_HERO);
                fill_rect(pixels, stride, px + CELL_SIZE / 2 - 4, py + 8, 8, 8, COLOR_WHITE);
            }

            if (x == enemy_x && y == enemy_y) {
                fill_rect(pixels, stride, px + 17, py + 17, CELL_SIZE - 34, CELL_SIZE - 34, COLOR_ENEMY);
                fill_rect(pixels, stride, px + 25, py + 25, CELL_SIZE - 50, CELL_SIZE - 50, COLOR_BG);
            }

            if (x == cursor_x && y == cursor_y) {
                fill_rect(pixels, stride, px + 4, py + 4, CELL_SIZE - 8, 4, COLOR_CURSOR);
                fill_rect(pixels, stride, px + 4, py + CELL_SIZE - 8, CELL_SIZE - 8, 4, COLOR_CURSOR);
                fill_rect(pixels, stride, px + 4, py + 4, 4, CELL_SIZE - 8, COLOR_CURSOR);
                fill_rect(pixels, stride, px + CELL_SIZE - 8, py + 4, 4, CELL_SIZE - 8, COLOR_CURSOR);
            }
        }
    }

    draw_ft4_probe(&canvas, pixels, stride, frame_tick);

    fill_rect(pixels, stride, 72, 590, FB_WIDTH - 144, 2, COLOR_GRID);
    fill_rect(pixels, stride, 72, 615, 42, 42, COLOR_HERO);
    fill_rect(pixels, stride, 132, 615, 42, 42, COLOR_ENEMY);
    fill_rect(pixels, stride, 192, 615, 42, 42, COLOR_CURSOR);
    draw_text(pixels, stride, 252, 622, "HERO ENEMY CURSOR", COLOR_WHITE, 1);
    draw_text(pixels, stride, 72, 674, "D-PAD MOVE  A SELECT  B CANCEL  PLUS EXIT", COLOR_MUTED, 1);

    /* Diagnostic heartbeat bar: changing length proves the framebuffer is being redrawn. */
    fill_rect(pixels, stride, 1000, 600, 96, 8, COLOR_GRID);
    fill_rect(pixels, stride, 1000, 600, 8 + (int)(frame_tick % 89), 8, COLOR_HERO);
    draw_text(pixels, stride, 1000, 612, "FRAME", COLOR_MUTED, 1);

    /* Small status indicator changes color while the unit is selected. */
    fill_rect(pixels, stride, FB_WIDTH - 116, 42, 44, 44,
              hero_selected ? COLOR_CURSOR : COLOR_HERO);
}


/*
 * Separate asset-free MAP02 tactical battle fixture.
 * No proprietary map layout, names, sprites or retail PS1 battle data.
 * Minus switches between the original input/texture smoke prototype and
 * this deterministic two-ally/two-enemy playable battle demonstration.
 */
static void draw_map02_battle(u32 *pixels, u32 stride,
                              const VhMap02Battle *battle, int scenario_id,
                              u32 frame_tick) {
    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    char count_label[] = "TURN 000";
    char scene_label[] = "MAP 1/2";
    scene_label[4] = (char)('1' + scenario_id);
    int x, y, unit;
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);
    draw_text(pixels, stride, 70, 24, "MAP02 BATTLE DEMO", COLOR_WHITE, 3);
    draw_text(pixels, stride, 70, 61, "ORIGINAL ASSET-FREE TACTICAL FIXTURE", COLOR_MUTED, 1);
    draw_text(pixels, stride, 70, 85,
              battle->status == VH_BWIN ? "VICTORY - Y RESET" :
              battle->status == VH_BLOSS ? "DEFEAT - Y RESET" :
              battle->selected >= 0 ? "CHOOSE MOVE OR ADJACENT ENEMY" :
                                      "SELECT AN AVAILABLE ALLY",
              battle->status == VH_BONGOING ? COLOR_HERO : COLOR_CURSOR, 1);
    count_label[5] = (char)('0' + (battle->turns_completed / 100) % 10);
    count_label[6] = (char)('0' + (battle->turns_completed / 10) % 10);
    count_label[7] = (char)('0' + battle->turns_completed % 10);
    draw_text(pixels, stride, 985, 145, count_label, COLOR_WHITE, 2);
    draw_text(pixels, stride, 985, 183, scene_label, COLOR_CURSOR, 2);
    for (y = 0; y < VH_BH; ++y) {
        for (x = 0; x < VH_BW; ++x) {
            const int px = GRID_X + x * CELL_SIZE, py = GRID_Y + y * CELL_SIZE;
            u32 tile = ((x + y) & 1) ? COLOR_TILE_ALT : COLOR_TILE;
            if (vh_bwall_at(battle, x, y))
                tile = COLOR_PANEL;
            else if (battle->selected >= 0 &&
                     vh_boccupant(battle, x, y, -1) < 0) {
                int d = vh_bpath(battle, battle->selected, x, y, -1, NULL, NULL);
                if (d >= 1 && d <= 2) tile = COLOR_RANGE;
            }
            vh_render_grid_tile(&canvas, px, py, CELL_SIZE,
                                (VhTilePalette){tile, COLOR_GRID});
            if (vh_bwall_at(battle, x, y)) {
                fill_rect(pixels, stride, px + 7, py + 7,
                          CELL_SIZE - 14, CELL_SIZE - 14, COLOR_GRID);
                fill_rect(pixels, stride, px + 14, py + 14,
                          CELL_SIZE - 28, CELL_SIZE - 28, COLOR_PANEL);
            }
            if (x == battle->cursor_x && y == battle->cursor_y) {
                vh_canvas_draw_rect_outline(&canvas, px + 3, py + 3,
                                            CELL_SIZE - 6, CELL_SIZE - 6,
                                            COLOR_CURSOR);
                vh_canvas_draw_rect_outline(&canvas, px + 7, py + 7,
                                            CELL_SIZE - 14, CELL_SIZE - 14,
                                            COLOR_CURSOR);
            }
        }
    }
    for (unit = 0; unit < VH_BUNITS; ++unit) {
        const VhBattleUnit *actor = &battle->units[unit];
        u32 color = unit < VH_BALLIES ? COLOR_HERO : COLOR_ENEMY;
        int px, py, hp, w;
        if (!vh_balive(actor)) continue;
        px = GRID_X + actor->x * CELL_SIZE;
        py = GRID_Y + actor->y * CELL_SIZE;
        if (unit < VH_BALLIES && actor->acted) color = COLOR_MUTED;
        fill_rect(pixels, stride, px + 17, py + 17, 38, 38, color);
        if (unit == battle->selected)
            vh_canvas_draw_rect_outline(&canvas, px + 11, py + 11, 50, 50, COLOR_WHITE);
        hp = actor->hp > 5 ? 5 : actor->hp;
        w = 8 * hp;
        fill_rect(pixels, stride, px + 16, py + 59, 40, 4, COLOR_PANEL);
        fill_rect(pixels, stride, px + 16, py + 59, w, 4, COLOR_CURSOR);
    }
    draw_text(pixels, stride, 985, 220, "ALLIES", COLOR_HERO, 2);
    draw_text(pixels, stride, 985, 262, "ENEMIES", COLOR_ENEMY, 2);
    draw_text(pixels, stride, 985, 322, "A SELECT", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 346, "B CANCEL", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 370, "X END TURN", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 394, "Y RESTART", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 418, "L R CHANGE MAP", COLOR_WHITE, 1);
    draw_text(pixels, stride, 70, 622, "MINUS SWITCH DEMO  PLUS EXIT", COLOR_MUTED, 2);
    draw_text(pixels, stride, 70, 661, "D-PAD CURSOR  A MOVE OR ATTACK  X ENEMY TURN", COLOR_MUTED, 1);
    fill_rect(pixels, stride, 1000, 610, 8 + (int)(frame_tick % 89), 6, COLOR_HERO);
}


/* Separate 4v4 capacity scene with independent original placeholder units.
 * Trigger ZR while in MAP02 battle mode; ZR again returns to old maps.
 * The default 2v2 renderer and its NeXium cursor paths are untouched. */
static void draw_map02_battle8(u32 *pixels, u32 stride,
                               const VhBattle8 *battle, u32 frame_tick) {
    const VhRoster8 *r = &battle->roster;
    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    char count_label[] = "TURN 000";
    int x, y, unit;
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);
    draw_text(pixels, stride, 70, 24, "MAP02 CAPACITY DEMO 4V4", COLOR_WHITE, 3);
    draw_text(pixels, stride, 70, 61,
              "ORIGINAL ASSET-FREE EIGHT-SLOT TEST", COLOR_MUTED, 1);
    draw_text(pixels, stride, 70, 85,
              battle->status == VH_BWIN ? "VICTORY - Y RESET" :
              battle->status == VH_BLOSS ? "DEFEAT - Y RESET" :
              battle->selected >= 0 ? "CHOOSE MOVE OR ADJACENT ENEMY" :
                                      "SELECT AN AVAILABLE ALLY",
              battle->status == VH_BONGOING ? COLOR_HERO : COLOR_CURSOR, 1);
    count_label[5] = (char)('0' + (battle->turns_completed / 100) % 10);
    count_label[6] = (char)('0' + (battle->turns_completed / 10) % 10);
    count_label[7] = (char)('0' + battle->turns_completed % 10);
    draw_text(pixels, stride, 985, 145, count_label, COLOR_WHITE, 2);
    draw_text(pixels, stride, 985, 183, "ROSTER 4 VS 4", COLOR_CURSOR, 1);
    for (y = 0; y < VH_BH; ++y) {
        for (x = 0; x < VH_BW; ++x) {
            const int px = GRID_X + x * CELL_SIZE, py = GRID_Y + y * CELL_SIZE;
            const int wall = !!(r->walls[y] & (1u << x));
            u32 tile = ((x + y) & 1) ? COLOR_TILE_ALT : COLOR_TILE;
            if (wall) tile = COLOR_PANEL;
            else if (battle->selected >= 0 &&
                     vh_r8_occupant(r, x, y) < 0) {
                const int d = vh_b8_path(battle, battle->selected,
                                         x, y, -1, NULL, NULL);
                if (d >= 1 && d <= battle->move_range)
                    tile = COLOR_RANGE;
            }
            vh_render_grid_tile(&canvas, px, py, CELL_SIZE,
                                (VhTilePalette){tile, COLOR_GRID});
            if (wall) {
                fill_rect(pixels, stride, px + 7, py + 7,
                          CELL_SIZE - 14, CELL_SIZE - 14, COLOR_GRID);
                fill_rect(pixels, stride, px + 14, py + 14,
                          CELL_SIZE - 28, CELL_SIZE - 28, COLOR_PANEL);
            }
            if (x == r->cursor_x && y == r->cursor_y) {
                vh_canvas_draw_rect_outline(&canvas, px + 3, py + 3,
                                            CELL_SIZE - 6, CELL_SIZE - 6,
                                            COLOR_CURSOR);
                vh_canvas_draw_rect_outline(&canvas, px + 7, py + 7,
                                            CELL_SIZE - 14, CELL_SIZE - 14,
                                            COLOR_CURSOR);
            }
        }
    }
    for (unit = 0; unit < VH_R8_CAPACITY; ++unit) {
        const VhBattleUnit *actor = &r->units[unit];
        u32 color = unit < VH_R8_SIDE_CAP ? COLOR_HERO : COLOR_ENEMY;
        int px, py, hp;
        if (!vh_r8_active(r, unit) || !vh_balive(actor)) continue;
        px = GRID_X + actor->x * CELL_SIZE;
        py = GRID_Y + actor->y * CELL_SIZE;
        if (unit < VH_R8_SIDE_CAP && actor->acted) color = COLOR_MUTED;
        fill_rect(pixels, stride, px + 17, py + 17, 38, 38, color);
        if (unit == battle->selected)
            vh_canvas_draw_rect_outline(&canvas, px + 11, py + 11,
                                        50, 50, COLOR_WHITE);
        hp = actor->hp > 5 ? 5 : actor->hp;
        fill_rect(pixels, stride, px + 16, py + 59, 40, 4, COLOR_PANEL);
        fill_rect(pixels, stride, px + 16, py + 59, 8 * hp, 4, COLOR_CURSOR);
    }
    draw_text(pixels, stride, 985, 220, "ALLIES", COLOR_HERO, 2);
    draw_text(pixels, stride, 985, 262, "ENEMIES", COLOR_ENEMY, 2);
    draw_text(pixels, stride, 985, 322, "A SELECT", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 346, "B CANCEL", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 370, "X END TURN", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 394, "Y RESTART", COLOR_WHITE, 1);
    draw_text(pixels, stride, 985, 418, "ZR OLD MAPS", COLOR_WHITE, 1);
    draw_text(pixels, stride, 70, 622,
              "ZR RETURN  MINUS SWITCH DEMO  PLUS EXIT", COLOR_MUTED, 2);
    draw_text(pixels, stride, 70, 661,
              "D-PAD CURSOR  A MOVE OR ATTACK  X ENEMY TURN", COLOR_MUTED, 1);
    fill_rect(pixels, stride, 1000, 610,
              8 + (int)(frame_tick % 89), 6, COLOR_HERO);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    Framebuffer fb;
    Result rc = framebufferCreate(&fb, nwindowGetDefault(), FB_WIDTH, FB_HEIGHT,
                                  PIXEL_FORMAT_RGBA_8888, 2);
    if (R_FAILED(rc)) return 1;

    rc = framebufferMakeLinear(&fb);
    if (R_FAILED(rc)) {
        framebufferClose(&fb);
        return 1;
    }

    init_ft4_probe_texture();
    VhGameState state = {1, 2, 1, 2, 6, 3, 0};
    VhMap02Battle battle;
    VhBattle8 battle8;
    int battle8_mode = 0;
    int battle_mode = 0;
    int scenario_id = 0;
    vh_binit(&battle);
    u32 frame_tick = 0;

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);

        unsigned int actions = 0;
        if (buttons_down & HidNpadButton_Left)  actions |= VH_INPUT_LEFT;
        if (buttons_down & HidNpadButton_Right) actions |= VH_INPUT_RIGHT;
        if (buttons_down & HidNpadButton_Up)    actions |= VH_INPUT_UP;
        if (buttons_down & HidNpadButton_Down)  actions |= VH_INPUT_DOWN;
        if (buttons_down & HidNpadButton_A)     actions |= VH_INPUT_CONFIRM;
        if (buttons_down & HidNpadButton_B)     actions |= VH_INPUT_CANCEL;
        if (buttons_down & HidNpadButton_Plus)  actions |= VH_INPUT_QUIT;

        if (buttons_down & HidNpadButton_Minus) {
            battle_mode = !battle_mode;
            battle8_mode = 0;
            if (battle_mode) {
                scenario_id = 0;  /* preserves existing NeXium default path */
                (void)vh_binit_index(&battle, scenario_id);
            }
        }
        if (battle_mode) {
            if (actions & VH_INPUT_QUIT) break;
            if (buttons_down & HidNpadButton_ZR) {
                if (battle8_mode) {
                    battle8_mode = 0;
                    (void)vh_binit_index(&battle, scenario_id);
                } else if (vh_b8_init(&battle8, &VH_MAP02_ROSTER8_SMOKE, 2, 2)) {
                    battle8_mode = 1;
                }
            }
            if (battle8_mode) {
                if (buttons_down & HidNpadButton_Y)
                    (void)vh_b8_init(&battle8, &VH_MAP02_ROSTER8_SMOKE, 2, 2);
                if (actions & VH_INPUT_LEFT)  vh_b8_cursor(&battle8, -1, 0);
                if (actions & VH_INPUT_RIGHT) vh_b8_cursor(&battle8, 1, 0);
                if (actions & VH_INPUT_UP)    vh_b8_cursor(&battle8, 0, -1);
                if (actions & VH_INPUT_DOWN)  vh_b8_cursor(&battle8, 0, 1);
                if (actions & VH_INPUT_CONFIRM) (void)vh_b8_choose(&battle8);
                if (actions & VH_INPUT_CANCEL) (void)vh_b8_cancel(&battle8);
                if (buttons_down & HidNpadButton_X)
                    (void)vh_b8_end_turn(&battle8);
            } else {
                if (buttons_down & (HidNpadButton_L | HidNpadButton_R)) {
                    int next = (scenario_id + 1) % VH_BSCENARIOS;
                    if (vh_binit_index(&battle, next)) scenario_id = next;
                }
                if (buttons_down & HidNpadButton_Y)
                    (void)vh_binit_index(&battle, scenario_id);
                if (actions & VH_INPUT_LEFT)  vh_bcursor(&battle, -1, 0);
                if (actions & VH_INPUT_RIGHT) vh_bcursor(&battle, 1, 0);
                if (actions & VH_INPUT_UP)    vh_bcursor(&battle, 0, -1);
                if (actions & VH_INPUT_DOWN)  vh_bcursor(&battle, 0, 1);
                if (actions & VH_INPUT_CONFIRM) (void)vh_bchoose(&battle);
                if (actions & VH_INPUT_CANCEL) (void)vh_bcancel(&battle);
                if (buttons_down & HidNpadButton_X)
                    (void)vh_bend_turn(&battle);
            }
        } else if (vh_process_input(&state, actions, GRID_WIDTH, GRID_HEIGHT,
                                    MOVE_RANGE)) {
            break;
        }

        u32 stride_bytes = 0;
        u32 *pixels = (u32 *)framebufferBegin(&fb, &stride_bytes);
        if (pixels) {
            const u32 stride_pixels = stride_bytes / sizeof(u32);
            if (battle_mode && battle8_mode)
                draw_map02_battle8(pixels, stride_pixels, &battle8, frame_tick++);
            else if (battle_mode)
                draw_map02_battle(pixels, stride_pixels, &battle,
                                  scenario_id, frame_tick++);
            else
                draw_frame(pixels, stride_pixels, state.cursor_x, state.cursor_y,
                           state.hero_x, state.hero_y, state.enemy_x, state.enemy_y,
                           state.hero_selected, frame_tick++);
        }
        framebufferEnd(&fb);
    }

    framebufferClose(&fb);
    return 0;
}
