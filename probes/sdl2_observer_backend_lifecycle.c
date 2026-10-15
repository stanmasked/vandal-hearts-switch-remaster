#include <SDL2/SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "switch_sdl2_observer_backend.h"

/* Resource-free lifecycle probe: no original Vandal Hearts data. */
int main(void) {
    VhSwitchSdl2ObserverBackend backend = {0};
    uint8_t pixels[12 * 9 * 3];
    int ok = 0;
    if (!vh_switch_sdl2_observer_backend_init(
            &backend, "VH SDL2 observer lifecycle", 1280, 720)) {
        fprintf(stderr, "observer backend init failed: %s\n", SDL_GetError());
        goto finish;
    }
    for (int i = 0; i < 3600; ++i) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) goto finish;
        }
        /* Bottom-up RGB24: stable corner markers, moving center blue. */
        for (int y = 0; y < 9; ++y)
            for (int x = 0; x < 12; ++x) {
                size_t at = ((size_t)y * 12u + (size_t)x) * 3u;
                pixels[at] = (uint8_t)(x * 18);
                pixels[at + 1] = (uint8_t)(y * 23);
                pixels[at + 2] = (uint8_t)(i * 3);
                if ((x < 2 || x >= 10) && (y < 2 || y >= 7)) {
                    int top = y >= 7;
                    int right = x >= 10;
                    pixels[at] = (uint8_t)(((top && !right) || (!top && right)) ? 255 : 0);
                    pixels[at + 1] = (uint8_t)(right ? 255 : 0);
                    pixels[at + 2] = (uint8_t)((!top && !right) ? 255 : 0);
                }
            }
        VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 12, 9);
        if (!vh_switch_observer_last_result()) {
            fprintf(stderr, "observer backend frame %d failed\n", i);
            goto finish;
        }
        SDL_Delay(16);
    }
    ok = 1;
finish:
    vh_switch_sdl2_observer_backend_shutdown(&backend);
    /* Unregistered observer must fail cleanly with no stale GL access. */
    VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 12, 9);
    if (vh_switch_observer_last_result() != 0) return 1;
    return ok ? 0 : 1;
}
