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
    for (int i = 0; i < 120; ++i) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) goto finish;
        }
        memset(pixels, (unsigned char)i, sizeof(pixels));
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
