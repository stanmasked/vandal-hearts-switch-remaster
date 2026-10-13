#include <switch.h>
#include <stdio.h>

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);

    PadState pad;
    padInitializeDefault(&pad);

    printf("Vandal Hearts Switch Remaster\n");
    printf("Homebrew toolchain smoke test\n\n");
    printf("This test contains no game code or game data.\n");
    printf("If you can read this, libnx console output works.\n\n");
    printf("Press + to exit.\n");

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttonsDown = padGetButtonsDown(&pad);
        if (buttonsDown & HidNpadButton_Plus) {
            break;
        }
        consoleUpdate(NULL);
    }

    consoleExit(NULL);
    return 0;
}
