#include <switch.h>
#include <stdio.h>

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    consoleClear();
    printf("Vandal Hearts - Switch prototype\n");
    printf("--------------------------------\n");
    printf("Minimal libnx input/console smoke test.\n");
    printf("Press A to confirm input.\n");
    printf("Press PLUS to exit.\n");

    bool a_pressed = false;

    while (appletMainLoop()) {
        hidScanInput();
        const u64 keys_down = hidKeysDown(CONTROLLER_P1_AUTO);

        if (keys_down & KEY_A) {
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

        if (keys_down & KEY_PLUS) {
            break;
        }
    }

    consoleExit(NULL);
    return 0;
}
