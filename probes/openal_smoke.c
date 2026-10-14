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

static void show_status(SDL_Renderer *renderer, int success) {
    if (!renderer) return;
    if (success) SDL_SetRenderDrawColor(renderer, 20, 180, 70, 255);
    else SDL_SetRenderDrawColor(renderer, 210, 35, 45, 255);
    SDL_RenderClear(renderer);
    SDL_RenderPresent(renderer);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    for (int i = 0; i < SAMPLE_COUNT; i++) {
        samples[i] = ((i % 50) < 25) ? 6000 : -6000;
    }

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
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
    show_status(renderer, 0);

    device = alcOpenDevice(NULL);
    if (!device) {
        fprintf(stderr, "alcOpenDevice failed\n");
        result = 3;
        goto cleanup;
    }

    context = alcCreateContext(device, NULL);
    if (!context) {
        fprintf(stderr, "alcCreateContext failed\n");
        result = 4;
        goto cleanup;
    }
    if (alcMakeContextCurrent(context) != ALC_TRUE) {
        fprintf(stderr, "alcMakeContextCurrent failed\n");
        result = 5;
        goto cleanup;
    }
    context_current = 1;

    alGenBuffers(1, &buffer);
    if (check_al_error("alGenBuffers") != 0) { result = 6; goto cleanup; }

    alBufferData(buffer, AL_FORMAT_MONO16, samples, (ALsizei)sizeof(samples), SAMPLE_RATE);
    if (check_al_error("alBufferData") != 0) { result = 7; goto cleanup; }

    alGenSources(1, &source);
    if (check_al_error("alGenSources") != 0) { result = 8; goto cleanup; }

    alSourcei(source, AL_BUFFER, (ALint)buffer);
    if (check_al_error("alSourcei(AL_BUFFER)") != 0) { result = 9; goto cleanup; }

    alSourcePlay(source);
    if (check_al_error("alSourcePlay") != 0) { result = 10; goto cleanup; }

    SDL_Delay(100);
    ALint source_state = AL_INITIAL;
    alGetSourcei(source, AL_SOURCE_STATE, &source_state);
    if (check_al_error("alGetSourcei(AL_SOURCE_STATE)") != 0) {
        result = 11;
        goto cleanup;
    }
    if (source_state != AL_PLAYING) {
        fprintf(stderr, "OpenAL source did not enter AL_PLAYING (state 0x%x)\n",
                (unsigned int)source_state);
        result = 12;
        goto cleanup;
    }

    fprintf(stderr, "OpenAL source entered AL_PLAYING successfully\n");

cleanup:
    show_status(renderer, result == 0);
    /* Keep the color-coded result on screen long enough for CI to capture it. */
    SDL_Delay(5000);
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
