#include <switch.h>
#include <stdio.h>

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    consoleInit(NULL);

    printf("Vandal Hearts Switch Remaster\n");
    printf("Homebrew toolchain smoke test\n\n");
    printf("This test contains no game code or game data.\n");
    printf("If you can read this, libnx console output works.\n\n");
    printf("Press + to exit.\n");

    while (appletMainLoop()) {
        hidScanInput();

        const u64 keysDown = hidKeysDown(CONTROLLER_P1_AUTO);
        if (keysDown & KEY_PLUS) {
            break;
        }

        consoleUpdate(NULL);
    }

    consoleExit(NULL);
    return 0;
}
