#include <switch.h>
#include <stdio.h>

#define GRID_WIDTH 8
#define GRID_HEIGHT 6

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);

    int cursor_x = GRID_WIDTH / 2;
    int cursor_y = GRID_HEIGHT / 2;
    int selected_x = -1;
    int selected_y = -1;

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);

        if ((buttons_down & HidNpadButton_Left) && cursor_x > 0) cursor_x--;
        if ((buttons_down & HidNpadButton_Right) && cursor_x < GRID_WIDTH - 1) cursor_x++;
        if ((buttons_down & HidNpadButton_Up) && cursor_y > 0) cursor_y--;
        if ((buttons_down & HidNpadButton_Down) && cursor_y < GRID_HEIGHT - 1) cursor_y++;

        if (buttons_down & HidNpadButton_A) {
            selected_x = cursor_x;
            selected_y = cursor_y;
        }
        if (buttons_down & HidNpadButton_B) {
            selected_x = -1;
            selected_y = -1;
        }

        consoleClear();
        printf("VANDAL HEARTS - SWITCH PROTOTYPE 0.2\n");
        printf("-----------------------------------\n");
        printf("Tactical grid input test\n\n");
        printf("  ");
        for (int x = 0; x < GRID_WIDTH; x++) printf("+---");
        printf("+\n");

        for (int y = 0; y < GRID_HEIGHT; y++) {
            printf("  ");
            for (int x = 0; x < GRID_WIDTH; x++) {
                char marker = ' ';
                if (x == cursor_x && y == cursor_y) marker = '@';
                else if (x == selected_x && y == selected_y) marker = 'X';
                printf("| %c ", marker);
            }
            printf("|\n  ");
            for (int x = 0; x < GRID_WIDTH; x++) printf("+---");
            printf("+\n");
        }

        printf("\nD-pad: move cursor   A: select tile\n");
        printf("B: clear selection   PLUS: exit\n");
        if (selected_x >= 0) {
            printf("Selected tile: (%d, %d)\n", selected_x + 1, selected_y + 1);
        } else {
            printf("Selected tile: none\n");
        }
        printf("\nBuild prototype only; no original game assets.\n");
        consoleUpdate(NULL);

        if (buttons_down & HidNpadButton_Plus) break;
    }

    consoleExit(NULL);
    return 0;
}
