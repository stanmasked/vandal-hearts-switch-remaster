#ifndef VH_SWITCH_SDL2_OBSERVER_BACKEND_H
#define VH_SWITCH_SDL2_OBSERVER_BACKEND_H

#include <SDL2/SDL.h>
#include "switch_upstream_observer.h"

/* Intermediate Switch SDL2/GLES2 backend, not an original-game entry point.
 * Single-threaded. Shut down before terminating SDL; registration is global.
 * Zero-initialize VhSwitchSdl2ObserverBackend before first init. A second init
 * on a live handle fails without changing or unregistering the active owner.
 */
typedef struct {
    SDL_Window *window;
    SDL_GLContext gl_context;
    VhSwitchRgb24Presenter presenter;
    int registered;
    int owns_sdl;
} VhSwitchSdl2ObserverBackend;

int vh_switch_sdl2_observer_backend_init(
    VhSwitchSdl2ObserverBackend *backend,
    const char *title, int width, int height);
void vh_switch_sdl2_observer_backend_shutdown(
    VhSwitchSdl2ObserverBackend *backend);

#endif
