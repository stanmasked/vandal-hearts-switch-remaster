#include <switch.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#define TEST_DIR "sdmc:/switch/vandal-hearts-switch-remaster"
#define TEST_FILE TEST_DIR "/fs-smoke-test.tmp"
#define TEST_PAYLOAD "vandal-hearts-switch-filesystem-smoke-v1"

static int ensure_directory(const char *path)
{
    if (mkdir(path, 0777) == 0 || errno == EEXIST)
        return 1;
    return 0;
}

static int run_filesystem_test(char *message, size_t message_size)
{
    FILE *file;
    char buffer[sizeof(TEST_PAYLOAD)];
    size_t count;
    int ok;

    Result rc = fsdevMountSdmc();
    if (R_FAILED(rc)) {
        snprintf(message, message_size, "fsdevMountSdmc failed: 0x%08lx", (unsigned long)rc);
        return 0;
    }

    if (!ensure_directory("sdmc:/switch") ||
        !ensure_directory(TEST_DIR)) {
        snprintf(message, message_size, "Cannot create test directory (errno=%d)", errno);
        fsdevUnmountDevice("sdmc");
        return 0;
    }

    file = fopen(TEST_FILE, "rb");
    if (file) {
        fclose(file);
        snprintf(message, message_size, "Refusing to overwrite existing test file");
        fsdevUnmountDevice("sdmc");
        return 0;
    }

    file = fopen(TEST_FILE, "wb");
    if (!file) {
        snprintf(message, message_size, "Cannot create test file (errno=%d)", errno);
        fsdevUnmountDevice("sdmc");
        return 0;
    }
    ok = fwrite(TEST_PAYLOAD, 1, sizeof(TEST_PAYLOAD), file) == sizeof(TEST_PAYLOAD);
    if (fflush(file) != 0)
        ok = 0;
    if (fclose(file) != 0)
        ok = 0;
    if (!ok) {
        remove(TEST_FILE);
        snprintf(message, message_size, "Write/flush/close failed");
        fsdevUnmountDevice("sdmc");
        return 0;
    }

    file = fopen(TEST_FILE, "rb");
    if (!file) {
        remove(TEST_FILE);
        snprintf(message, message_size, "Cannot reopen test file (errno=%d)", errno);
        fsdevUnmountDevice("sdmc");
        return 0;
    }
    count = fread(buffer, 1, sizeof(buffer), file);
    ok = count == sizeof(TEST_PAYLOAD) &&
         memcmp(buffer, TEST_PAYLOAD, sizeof(TEST_PAYLOAD)) == 0 &&
         fgetc(file) == EOF && !ferror(file);
    if (fclose(file) != 0)
        ok = 0;

    if (remove(TEST_FILE) != 0)
        ok = 0;
    fsdevUnmountDevice("sdmc");

    snprintf(message, message_size, "%s", ok ? "PASS: write/read/compare/remove" :
                                            "FAIL: readback or cleanup failed");
    return ok;
}

int main(int argc, char *argv[])
{
    char message[160] = "Not run";
    int passed;
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    printf("Vandal Hearts Switch Remaster\n");
    printf("Filesystem smoke test\n\n");
    printf("This test writes and removes one temporary file on SD card.\n");
    printf("It refuses to overwrite an existing test file.\n\n");

    passed = run_filesystem_test(message, sizeof(message));
    printf("%s\n\n", message);
    printf("Press + to exit.\n");

    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus)
            break;
        consoleUpdate(NULL);
    }

    consoleExit(NULL);
    return passed ? 0 : 1;
}
