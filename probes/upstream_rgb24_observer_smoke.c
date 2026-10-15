#include <SDL2/SDL.h>
#include <SDL2/SDL_opengles2.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "switch_upstream_observer.h"

/* Synthetic render probe only: no original game data included. */
typedef struct {
    SDL_Window *window;
    SDL_GLContext context;
} WindowState;

static int query_viewport(void *opaque, int *width, int *height) {
    WindowState *state = (WindowState *)opaque;
    if (!state || !state->window || !width || !height) return 0;
    SDL_GL_GetDrawableSize(state->window, width, height);
    return *width > 0 && *height > 0;
}

static int swap_buffers(void *opaque) {
    WindowState *state = (WindowState *)opaque;
    if (!state || !state->window) return 0;
    SDL_GL_SwapWindow(state->window);
    return 1;
}

int main(void) {
    WindowState state = {0};
    VhSwitchRgb24Presenter presenter = {0};
    VhSwitchPresentHook hook;
    uint8_t pixels[9 * 7 * 3];
    int frame = 0;
    int running = 1;
    int ok = 0;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK) != 0) goto done;
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
    state.window = SDL_CreateWindow("VH upstream RGB24 hook probe",
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, 1280, 720,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!state.window) goto done;
    state.context = SDL_GL_CreateContext(state.window);
    if (!state.context) goto done;
    if (SDL_GL_MakeCurrent(state.window, state.context) != 0) goto done;
    if (!vh_switch_rgb24_presenter_init(&presenter)) goto done;

    hook.presenter = &presenter;
    hook.query_viewport = query_viewport;
    hook.swap_buffers = swap_buffers;
    hook.context = &state;
    if (!vh_switch_observer_register(&hook)) goto done;

    while (running && frame < 3600) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT || event.type == SDL_KEYDOWN)
                running = 0;
        }
        for (int y = 0; y < 7; ++y)
            for (int x = 0; x < 9; ++x) {
                size_t at = ((size_t)y * 9u + (size_t)x) * 3u;
                pixels[at] = (uint8_t)(x * 24);
                pixels[at + 1] = (uint8_t)(y * 31);
                pixels[at + 2] = (uint8_t)(frame * 3);
                /* Four fixed RGB markers in bottom-up buffer coordinates. */
                if ((x < 2 || x >= 7) && (y < 2 || y >= 5)) {
                    int top = y >= 5;
                    int right = x >= 7;
                    pixels[at] = (uint8_t)((top && !right) || (!top && right) ? 255 : 0);
                    pixels[at + 1] = (uint8_t)(right ? 255 : 0);
                    pixels[at + 2] = (uint8_t)((!top && !right) ? 255 : 0);
                }
            }
        VH_ObserveCompletedRGB24(pixels, sizeof(pixels), 9, 7);
        if (!vh_switch_observer_last_result()) {
            fprintf(stderr, "RGB24 observer present failed at frame %d\n", frame);
            goto done;
        }
        ++frame;
        SDL_Delay(16);
    }
    ok = 1;
done:
    vh_switch_observer_unregister();
    if (state.context) {
        if (presenter.initialized) vh_switch_rgb24_presenter_destroy(&presenter);
        SDL_GL_DeleteContext(state.context);
    }
    if (state.window) SDL_DestroyWindow(state.window);
    SDL_Quit();
    return ok ? 0 : 1;
}
