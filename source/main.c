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

static void draw_frame(u32 *pixels, u32 stride, int cursor_x, int cursor_y,
                       int hero_x, int hero_y, int enemy_x, int enemy_y,
                       int hero_selected) {
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);

    /* Header and footer panels are deliberately graphical: no font/assets required. */
    fill_rect(pixels, stride, 72, 42, FB_WIDTH - 144, 8, COLOR_HERO);
    fill_rect(pixels, stride, 72, 62, 330, 10, COLOR_WHITE);
    fill_rect(pixels, stride, 72, 82, 210, 6, COLOR_MUTED);

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
    fill_rect(pixels, stride, 252, 622, 250, 8, COLOR_WHITE);
    fill_rect(pixels, stride, 252, 640, 330, 6, COLOR_MUTED);

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
