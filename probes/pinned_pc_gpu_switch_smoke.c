/* Resource-free Switch/Nexium integration test: calls the pinned upstream
 * PC_GpuPresent BGR555 conversion and presents its RGB24 through the real
 * SDL2/GLES2 observer backend. Not original gameplay.
 */
#include <SDL2/SDL.h>
#include <stdint.h>
#include <stdio.h>
#include "switch_sdl2_observer_backend.h"

extern int PC_GpuInit(int width, int height, const char *title);
extern void PC_GpuGetWindowSize(int *width, int *height, int *scale);
extern void PC_GpuPresent(unsigned short *vram, int vramW, int vramH,
                          int x, int y, int w, int h);

/* Test-only game-service substitutes: no game logic or original assets.
 * LTO removes unreachable desktop menu/subtitle paths. These must never be
 * linked into the eventual real game build. */
int PC_MovieSubsLoaded(void) { return 0; }
int PC_OverlayIsOpen(void) { return 0; }
int PC_BattleSpeedGet(void) { return 1; }

int main(void) {
    VhSwitchSdl2ObserverBackend backend = {0};
    unsigned short vram[12 * 9];
    int ok = 0;
    /* Original GPU init must never open a competing SDL/desktop GL window. */
    if (PC_GpuInit(320, 240, "must not create desktop window")) {
        fprintf(stderr, "PC_GpuInit unexpectedly succeeded before Switch backend\n");
        goto finish;
    }
    if (!vh_switch_sdl2_observer_backend_init(
            &backend, "VH pinned GPU Switch probe", 1280, 720)) {
        fprintf(stderr, "pinned GPU backend initialization failed: %s\n",
                SDL_GetError());
        goto finish;
    }
    {
        int drawable_w = 0, drawable_h = 0, scale = 0;
        if (!PC_GpuInit(320, 240, "Switch owned context")) {
            fprintf(stderr, "Pinned PC_GpuInit failed to accept Switch backend\n");
            goto finish;
        }
        PC_GpuGetWindowSize(&drawable_w, &drawable_h, &scale);
        if (drawable_w != 1280 || drawable_h != 720 || scale != 1) {
            fprintf(stderr, "Pinned GPU target dimensions: %dx%d scale=%d\n",
                    drawable_w, drawable_h, scale);
            goto finish;
        }
        fprintf(stderr, "Pinned GPU init accepted Switch backend: %dx%d\n",
                drawable_w, drawable_h);
    }
    for (int frame = 0; frame < 3600; ++frame) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) goto finish;
        }
        for (int y = 0; y < 9; ++y) {
            for (int x = 0; x < 12; ++x) {
                unsigned r = (unsigned)x * 2u;
                unsigned g = (unsigned)(8 - y) * 3u;
                unsigned blue = (unsigned)(frame / 3) % 32u;
                if ((x < 2 || x >= 10) && (y < 2 || y >= 7)) {
                    int top = y < 2;
                    int right = x >= 10;
                    r = (top && !right) || (!top && right) ? 31u : 0u;
                    g = right ? 31u : 0u;
                    blue = (!top && !right) ? 31u : 0u;
                }
                vram[y * 12 + x] = (unsigned short)(r | (g << 5) | (blue << 10));
            }
        }
        PC_GpuPresent(vram, 12, 9, 0, 0, 12, 9);
        if (!vh_switch_observer_last_result()) {
            fprintf(stderr, "Pinned PC_GpuPresent did not deliver frame %d\n",
                    frame);
            goto finish;
        }
        SDL_Delay(16);
    }
    ok = 1;
finish:
    vh_switch_sdl2_observer_backend_shutdown(&backend);
    return ok ? 0 : 1;
}
