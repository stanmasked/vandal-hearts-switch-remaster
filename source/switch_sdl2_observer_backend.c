#include "switch_sdl2_observer_backend.h"

#include <string.h>

static int backend_viewport(void *opaque, int *width, int *height) {
    VhSwitchSdl2ObserverBackend *backend = (VhSwitchSdl2ObserverBackend *)opaque;
    if (!backend || !backend->window || !width || !height) return 0;
    SDL_GL_GetDrawableSize(backend->window, width, height);
    return *width > 0 && *height > 0;
}

static int backend_swap(void *opaque) {
    VhSwitchSdl2ObserverBackend *backend = (VhSwitchSdl2ObserverBackend *)opaque;
    if (!backend || !backend->window || !backend->gl_context) return 0;
    if (SDL_GL_GetCurrentContext() != backend->gl_context) return 0;
    SDL_GL_SwapWindow(backend->window);
    return 1;
}

void vh_switch_sdl2_observer_backend_shutdown(
    VhSwitchSdl2ObserverBackend *backend) {
    if (!backend) return;
    if (backend->registered) vh_switch_observer_unregister();
    if (backend->gl_context) {
        SDL_GL_MakeCurrent(backend->window, backend->gl_context);
        vh_switch_rgb24_presenter_destroy(&backend->presenter);
        SDL_GL_DeleteContext(backend->gl_context);
    }
    if (backend->window) SDL_DestroyWindow(backend->window);
    if (backend->owns_sdl) SDL_QuitSubSystem(SDL_INIT_VIDEO);
    memset(backend, 0, sizeof(*backend));
}

int vh_switch_sdl2_observer_backend_init(
    VhSwitchSdl2ObserverBackend *backend,
    const char *title, int width, int height) {
    VhSwitchPresentHook hook;
    if (!backend || !title || width <= 0 || height <= 0) return 0;
    memset(backend, 0, sizeof(*backend));
    /* SDL may already be initialized by the game's existing input layer. */
    if (!(SDL_WasInit(SDL_INIT_VIDEO) & SDL_INIT_VIDEO)) {
        if (SDL_InitSubSystem(SDL_INIT_VIDEO) != 0) return 0;
        backend->owns_sdl = 1;
    }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_PROFILE_MASK, SDL_GL_CONTEXT_PROFILE_ES);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 0);
    backend->window = SDL_CreateWindow(title,
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, width, height,
        SDL_WINDOW_OPENGL | SDL_WINDOW_SHOWN);
    if (!backend->window) goto fail;
    backend->gl_context = SDL_GL_CreateContext(backend->window);
    if (!backend->gl_context) goto fail;
    if (SDL_GL_MakeCurrent(backend->window, backend->gl_context) != 0) goto fail;
    if (!vh_switch_rgb24_presenter_init(&backend->presenter)) goto fail;
    hook.presenter = &backend->presenter;
    hook.query_viewport = backend_viewport;
    hook.swap_buffers = backend_swap;
    hook.context = backend;
    if (!vh_switch_observer_register(&hook)) goto fail;
    backend->registered = 1;
    return 1;
fail:
    vh_switch_sdl2_observer_backend_shutdown(backend);
    return 0;
}
