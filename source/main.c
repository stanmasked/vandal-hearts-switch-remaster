#include <switch.h>
#include <string.h>

#include "game_rules.h"

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

static void fill_rect(u32 *pixels, u32 stride, int x, int y, int width, int height, u32 color) {
    if (x < 0) { width += x; x = 0; }
    if (y < 0) { height += y; y = 0; }
    if (x + width > FB_WIDTH) width = FB_WIDTH - x;
    if (y + height > FB_HEIGHT) height = FB_HEIGHT - y;
    if (width <= 0 || height <= 0) return;

    for (int row = y; row < y + height; row++) {
        u32 *line = pixels + (u32)row * stride;
        for (int col = x; col < x + width; col++) line[col] = color;
    }
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

static void draw_frame(u32 *pixels, u32 stride, int cursor_x, int cursor_y,
                       int hero_x, int hero_y, int enemy_x, int enemy_y,
                       int hero_selected) {
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);

    /* Compact bitmap labels keep the prototype self-contained and asset-free. */
    draw_text(pixels, stride, 72, 28, "VANDAL HEARTS", COLOR_WHITE, 3);
    draw_text(pixels, stride, 72, 59, "TACTICAL PROTOTYPE", COLOR_MUTED, 1);
    draw_text(pixels, stride, 700, 59,
              hero_selected ? "CHOOSE DESTINATION" : "SELECT HERO",
              COLOR_WHITE, 1);
    fill_rect(pixels, stride, 72, 82, FB_WIDTH - 144, 2, COLOR_HERO);

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

            fill_rect(pixels, stride, px + 2, py + 2, CELL_SIZE - 4, CELL_SIZE - 4, tile);
            fill_rect(pixels, stride, px, py, CELL_SIZE, 2, COLOR_GRID);
            fill_rect(pixels, stride, px, py + CELL_SIZE - 2, CELL_SIZE, 2, COLOR_GRID);
            fill_rect(pixels, stride, px, py, 2, CELL_SIZE, COLOR_GRID);
            fill_rect(pixels, stride, px + CELL_SIZE - 2, py, 2, CELL_SIZE, COLOR_GRID);

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

    fill_rect(pixels, stride, 72, 590, FB_WIDTH - 144, 2, COLOR_GRID);
    fill_rect(pixels, stride, 72, 615, 42, 42, COLOR_HERO);
    fill_rect(pixels, stride, 132, 615, 42, 42, COLOR_ENEMY);
    fill_rect(pixels, stride, 192, 615, 42, 42, COLOR_CURSOR);
    draw_text(pixels, stride, 252, 622, "HERO ENEMY CURSOR", COLOR_WHITE, 1);
    draw_text(pixels, stride, 72, 674, "D-PAD MOVE  A SELECT  B CANCEL  PLUS EXIT", COLOR_MUTED, 1);

    /* Small status indicator changes color while the unit is selected. */
    fill_rect(pixels, stride, FB_WIDTH - 116, 42, 44, 44,
              hero_selected ? COLOR_CURSOR : COLOR_HERO);
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

    int cursor_x = 1;
    int cursor_y = 2;
    int hero_x = 1;
    int hero_y = 2;
    const int enemy_x = 6;
    const int enemy_y = 3;
    int hero_selected = 0;

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);

        if (buttons_down & HidNpadButton_Plus) break;
        if ((buttons_down & HidNpadButton_Left) && cursor_x > 0) cursor_x--;
        if ((buttons_down & HidNpadButton_Right) && cursor_x < GRID_WIDTH - 1) cursor_x++;
        if ((buttons_down & HidNpadButton_Up) && cursor_y > 0) cursor_y--;
        if ((buttons_down & HidNpadButton_Down) && cursor_y < GRID_HEIGHT - 1) cursor_y++;

        if (buttons_down & HidNpadButton_A) {
            if (!hero_selected) {
                if (cursor_x == hero_x && cursor_y == hero_y) hero_selected = 1;
            } else if (vh_can_move(hero_x, hero_y, cursor_x, cursor_y,
                                   GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE, enemy_x, enemy_y)) {
                hero_x = cursor_x;
                hero_y = cursor_y;
                hero_selected = 0;
            }
        }

        if (buttons_down & HidNpadButton_B) hero_selected = 0;

        u32 stride_bytes = 0;
        u32 *pixels = (u32 *)framebufferBegin(&fb, &stride_bytes);
        if (pixels) {
            const u32 stride_pixels = stride_bytes / sizeof(u32);
            draw_frame(pixels, stride_pixels, cursor_x, cursor_y, hero_x, hero_y,
                       enemy_x, enemy_y, hero_selected);
        }
        framebufferEnd(&fb);
    }

    framebufferClose(&fb);
    return 0;
}
