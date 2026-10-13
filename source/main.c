#include <switch.h>
#include <stdio.h>

#include "game_rules.h"

#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define MOVE_RANGE 2

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);

    int cursor_x = 1;
    int cursor_y = 2;
    int hero_x = 1;
    int hero_y = 2;
    const int enemy_x = 6;
    const int enemy_y = 3;
    int hero_selected = 0;
    const char *message = "Move cursor to P and press A to select.";

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);

        if ((buttons_down & HidNpadButton_Left) && cursor_x > 0) cursor_x--;
        if ((buttons_down & HidNpadButton_Right) && cursor_x < GRID_WIDTH - 1) cursor_x++;
        if ((buttons_down & HidNpadButton_Up) && cursor_y > 0) cursor_y--;
        if ((buttons_down & HidNpadButton_Down) && cursor_y < GRID_HEIGHT - 1) cursor_y++;

        if (buttons_down & HidNpadButton_A) {
            if (!hero_selected) {
                if (cursor_x == hero_x && cursor_y == hero_y) {
                    hero_selected = 1;
                    message = "Unit selected: move within 2 tiles, then press A.";
                } else {
                    message = "No unit on this tile. Move cursor to P.";
                }
            } else if (cursor_x == enemy_x && cursor_y == enemy_y) {
                message = "Enemy tile is blocked.";
            } else if (vh_manhattan_distance(hero_x, hero_y, cursor_x, cursor_y) > MOVE_RANGE) {
                message = "Too far: movement range is 2 tiles.";
            } else if (!vh_can_move(hero_x, hero_y, cursor_x, cursor_y,
                                   GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE, enemy_x, enemy_y)) {
                message = "Invalid destination.";
            } else {
                hero_x = cursor_x;
                hero_y = cursor_y;
                hero_selected = 0;
                message = "Unit moved. Select P again for another test move.";
            }
        }

        if (buttons_down & HidNpadButton_B) {
            hero_selected = 0;
            message = "Selection cancelled.";
        }

        consoleClear();
        printf("VANDAL HEARTS - SWITCH PROTOTYPE 0.3\n");
        printf("-----------------------------------\n");
        printf("Tactical movement test | Range: %d\n\n", MOVE_RANGE);
        printf("  ");
        for (int x = 0; x < GRID_WIDTH; x++) printf("+---");
        printf("+\n");

        for (int y = 0; y < GRID_HEIGHT; y++) {
            printf("  ");
            for (int x = 0; x < GRID_WIDTH; x++) {
                char marker = '.';
                if (x == hero_x && y == hero_y) marker = hero_selected ? 'S' : 'P';
                if (x == enemy_x && y == enemy_y) marker = 'E';
                if (x == cursor_x && y == cursor_y) marker = '@';
                printf("| %c ", marker);
            }
            printf("|\n  ");
            for (int x = 0; x < GRID_WIDTH; x++) printf("+---");
            printf("+\n");
        }

        printf("\nD-pad: move cursor   A: select/move unit\n");
        printf("B: cancel selection  PLUS: exit\n");
        printf("P=hero  E=enemy  @=cursor  S=selected hero\n");
        printf("%s\n", message);
        printf("Generated test only; no original game assets.\n");
        consoleUpdate(NULL);

        if (buttons_down & HidNpadButton_Plus) break;
    }

    consoleExit(NULL);
    return 0;
}
