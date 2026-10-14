#include <SDL.h>
#include <AL/al.h>
#include <AL/alc.h>
#include <stdio.h>

#define SAMPLE_RATE 22050
#define SAMPLE_COUNT 11025

static ALshort samples[SAMPLE_COUNT];

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    /* Generated square-wave tone: no audio files or game assets are needed. */
    for (int i = 0; i < SAMPLE_COUNT; i++) {
        samples[i] = ((i % 50) < 25) ? 6000 : -6000;
    }

    if (SDL_Init(SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "SDL_Init audio failed: %s\n", SDL_GetError());
        return 1;
    }

    ALCdevice *device = alcOpenDevice(NULL);
    if (!device) {
        fprintf(stderr, "alcOpenDevice failed\n");
        SDL_Quit();
        return 2;
    }

    ALCcontext *context = alcCreateContext(device, NULL);
    if (!context) {
        fprintf(stderr, "alcCreateContext failed\n");
        alcCloseDevice(device);
        SDL_Quit();
        return 3;
    }
    if (alcMakeContextCurrent(context) != ALC_TRUE) {
        fprintf(stderr, "alcMakeContextCurrent failed\n");
        alcDestroyContext(context);
        alcCloseDevice(device);
        SDL_Quit();
        return 4;
    }

    ALuint buffer = 0;
    ALuint source = 0;
    alGenBuffers(1, &buffer);
    alBufferData(buffer, AL_FORMAT_MONO16, samples, (ALsizei)sizeof(samples), SAMPLE_RATE);
    alGenSources(1, &source);
    alSourcei(source, AL_BUFFER, (ALint)buffer);
    alSourcePlay(source);

    /* Runtime test: the tone should be audible once, then the app exits. */
    SDL_Delay(650);

    alSourceStop(source);
    alDeleteSources(1, &source);
    alDeleteBuffers(1, &buffer);
    alcMakeContextCurrent(NULL);
    alcDestroyContext(context);
    alcCloseDevice(device);
    SDL_Quit();
    return 0;
}
