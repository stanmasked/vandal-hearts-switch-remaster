#include <switch.h>
#include <stdint.h>

#define FB_WIDTH  1280
#define FB_HEIGHT 720

int main(int argc, char *argv[])
{
    (void)argc;
    (void)argv;

    NWindow *window = nwindowGetDefault();
    Framebuffer fb;
    framebufferCreate(&fb, window, FB_WIDTH, FB_HEIGHT, PIXEL_FORMAT_RGBA_8888, 2);
    framebufferMakeLinear(&fb);

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    while (appletMainLoop()) {
        padUpdate(&pad);
        if (padGetButtonsDown(&pad) & HidNpadButton_Plus)
            break;

        u32 stride = 0;
        u32 *pixels = (u32 *)framebufferBegin(&fb, &stride);
        if (pixels) {
            const u32 stride_pixels = stride / sizeof(u32);
            for (u32 y = 0; y < FB_HEIGHT; y++) {
                for (u32 x = 0; x < FB_WIDTH; x++) {
                    const u32 band = (x * 6u) / FB_WIDTH;
                    const u32 color = (band == 0) ? RGBA8_MAXALPHA(255, 0, 0)
                                     : (band == 1) ? RGBA8_MAXALPHA(255, 128, 0)
                                     : (band == 2) ? RGBA8_MAXALPHA(255, 255, 0)
                                     : (band == 3) ? RGBA8_MAXALPHA(0, 200, 0)
                                     : (band == 4) ? RGBA8_MAXALPHA(0, 80, 255)
                                                   : RGBA8_MAXALPHA(160, 0, 255);
                    pixels[y * stride_pixels + x] = color;
                }
            }
            framebufferEnd(&fb);
        }
    }

    framebufferClose(&fb);
    return 0;
}
