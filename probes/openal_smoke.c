#include <SDL.h>
#include <AL/al.h>
#include <AL/alc.h>
#include <stdio.h>

#define SAMPLE_RATE 22050
#define SAMPLE_COUNT 11025

static ALshort samples[SAMPLE_COUNT];

static int check_al_error(const char *operation) {
    const ALenum error = alGetError();
    if (error == AL_NO_ERROR) return 0;

    fprintf(stderr, "%s failed with OpenAL error 0x%x\n",
            operation, (unsigned int)error);
    return -1;
}

static void show_status(SDL_Renderer *renderer, int result) {
    if (!renderer) return;

    /* Distinct full-screen colors let headless CI identify guest-side failures
       even when the emulator does not forward the NRO's stderr. */
    switch (result) {
        case 0:  SDL_SetRenderDrawColor(renderer, 20, 180, 70, 255); break;
        case 1:  SDL_SetRenderDrawColor(renderer, 210, 35, 45, 255); break; /* SDL init */
        case 2:  SDL_SetRenderDrawColor(renderer, 220, 110, 20, 255); break; /* display */
        case 3:  SDL_SetRenderDrawColor(renderer, 150, 40, 190, 255); break; /* OpenAL device */
        case 4:  SDL_SetRenderDrawColor(renderer, 30, 100, 210, 255); break; /* context */
        case 5:  SDL_SetRenderDrawColor(renderer, 20, 180, 200, 255); break; /* current context */
        case 6:  SDL_SetRenderDrawColor(renderer, 230, 190, 20, 255); break; /* buffer gen */
        case 7:  SDL_SetRenderDrawColor(renderer, 120, 190, 40, 255); break; /* buffer data */
        case 8:  SDL_SetRenderDrawColor(renderer, 230, 100, 150, 255); break; /* source gen */
        case 9:  SDL_SetRenderDrawColor(renderer, 110, 80, 220, 255); break; /* source buffer */
        case 10: SDL_SetRenderDrawColor(renderer, 255, 130, 0, 255); break; /* play */
        case 11: SDL_SetRenderDrawColor(renderer, 0, 130, 130, 255); break; /* query */
        case 12: SDL_SetRenderDrawColor(renderer, 255, 0, 180, 255); break; /* not playing */
        default: SDL_SetRenderDrawColor(renderer, 80, 80, 80, 255); break;
    }
    SDL_RenderClear(renderer);
    SDL_RenderPresent(renderer);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    for (int i = 0; i < SAMPLE_COUNT; i++) {
        samples[i] = ((i % 50) < 25) ? 6000 : -6000;
    }

    if (SDL_Init(SDL_INIT_VIDEO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window *window = SDL_CreateWindow(
        "OpenAL playback status", SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        1280, 720, SDL_WINDOW_SHOWN);
    SDL_Renderer *renderer = window ? SDL_CreateRenderer(
        window, -1, SDL_RENDERER_SOFTWARE) : NULL;

    int result = 0;
    ALCdevice *device = NULL;
    ALCcontext *context = NULL;
    ALuint buffer = 0;
    ALuint source = 0;
    int context_current = 0;

    if (!window || !renderer) {
        fprintf(stderr, "SDL status display failed: %s\n", SDL_GetError());
        result = 2;
        goto cleanup;
    }
    show_status(renderer, 1);

    show_status(renderer, 3); /* entering alcOpenDevice */
    device = alcOpenDevice(NULL);
    if (!device) {
        fprintf(stderr, "alcOpenDevice failed\n");
        result = 3;
        goto cleanup;
    }

    show_status(renderer, 4); /* entering alcCreateContext */
    context = alcCreateContext(device, NULL);
    if (!context) {
        fprintf(stderr, "alcCreateContext failed\n");
        result = 4;
        goto cleanup;
    }
    show_status(renderer, 5); /* entering alcMakeContextCurrent */
    if (alcMakeContextCurrent(context) != ALC_TRUE) {
        fprintf(stderr, "alcMakeContextCurrent failed\n");
        result = 5;
        goto cleanup;
    }
    context_current = 1;

    show_status(renderer, 6); /* entering alGenBuffers */
    alGenBuffers(1, &buffer);
    if (check_al_error("alGenBuffers") != 0) { result = 6; goto cleanup; }

    show_status(renderer, 7); /* entering alBufferData */
    alBufferData(buffer, AL_FORMAT_MONO16, samples, (ALsizei)sizeof(samples), SAMPLE_RATE);
    if (check_al_error("alBufferData") != 0) { result = 7; goto cleanup; }

    show_status(renderer, 8); /* entering alGenSources */
    alGenSources(1, &source);
    if (check_al_error("alGenSources") != 0) { result = 8; goto cleanup; }

    show_status(renderer, 9); /* entering alSourcei */
    alSourcei(source, AL_BUFFER, (ALint)buffer);
    if (check_al_error("alSourcei(AL_BUFFER)") != 0) { result = 9; goto cleanup; }

    show_status(renderer, 10); /* entering alSourcePlay */
    alSourcePlay(source);
    if (check_al_error("alSourcePlay") != 0) { result = 10; goto cleanup; }

    /* alGetSourcei(AL_SOURCE_STATE) stalls in the current NeXium runtime.
       Keep this probe focused on whether the playback request itself returns;
       this does NOT prove audible output or AL_PLAYING state. */
    SDL_Delay(100);
    fprintf(stderr, "OpenAL alSourcePlay returned without an AL error; audible output is not verified\\n");

cleanup:
    show_status(renderer, result);
    /* Keep the color-coded result on screen long enough for CI to capture it. */
    SDL_Delay(15000);
    if (context_current) {
        if (source != 0) {
            alSourceStop(source);
            alDeleteSources(1, &source);
            if (check_al_error("source cleanup") != 0) result = result ? result : 13;
        }
        if (buffer != 0) {
            alDeleteBuffers(1, &buffer);
            if (check_al_error("buffer cleanup") != 0) result = result ? result : 14;
        }
        alcMakeContextCurrent(NULL);
    }
    if (context) alcDestroyContext(context);
    if (device) alcCloseDevice(device);
    if (renderer) SDL_DestroyRenderer(renderer);
    if (window) SDL_DestroyWindow(window);
    SDL_Quit();
    return result;
}
