#include <switch.h>
#include <stdio.h>

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);

    bool a_pressed = false;

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);

        if (buttons_down & HidNpadButton_A) {
            a_pressed = true;
        }

        consoleClear();
        printf("Vandal Hearts - Switch prototype\n");
        printf("--------------------------------\n");
        printf("Minimal libnx input/console smoke test.\n");
        printf("A button detected: %s\n", a_pressed ? "YES" : "NO");
        printf("Press A to confirm input.\n");
        printf("Press PLUS to exit.\n");
        consoleUpdate(NULL);

        if (buttons_down & HidNpadButton_Plus) {
            break;
        }
    }

    consoleExit(NULL);
    return 0;
}
