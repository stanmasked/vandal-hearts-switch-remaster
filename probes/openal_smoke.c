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

    int result = 0;
    ALCdevice *device = alcOpenDevice(NULL);
    ALCcontext *context = NULL;
    ALuint buffer = 0;
    ALuint source = 0;
    int context_current = 0;

    if (!device) {
        fprintf(stderr, "alcOpenDevice failed\n");
        result = 2;
        goto cleanup;
    }

    context = alcCreateContext(device, NULL);
    if (!context) {
        fprintf(stderr, "alcCreateContext failed\n");
        result = 3;
        goto cleanup;
    }
    if (alcMakeContextCurrent(context) != ALC_TRUE) {
        fprintf(stderr, "alcMakeContextCurrent failed\n");
        result = 4;
        goto cleanup;
    }
    context_current = 1;

    alGenBuffers(1, &buffer);
    if (check_al_error("alGenBuffers") != 0) {
        result = 5;
        goto cleanup;
    }

    alBufferData(buffer, AL_FORMAT_MONO16, samples, (ALsizei)sizeof(samples), SAMPLE_RATE);
    if (check_al_error("alBufferData") != 0) {
        result = 6;
        goto cleanup;
    }

    alGenSources(1, &source);
    if (check_al_error("alGenSources") != 0) {
        result = 7;
        goto cleanup;
    }

    alSourcei(source, AL_BUFFER, (ALint)buffer);
    if (check_al_error("alSourcei(AL_BUFFER)") != 0) {
        result = 8;
        goto cleanup;
    }

    alSourcePlay(source);
    if (check_al_error("alSourcePlay") != 0) {
        result = 9;
        goto cleanup;
    }

    /* Check playback before the generated 0.5-second buffer can finish. */
    SDL_Delay(100);
    ALint source_state = AL_INITIAL;
    alGetSourcei(source, AL_SOURCE_STATE, &source_state);
    if (check_al_error("alGetSourcei(AL_SOURCE_STATE)") != 0) {
        result = 10;
        goto cleanup;
    }
    if (source_state != AL_PLAYING) {
        fprintf(stderr, "OpenAL source did not enter AL_PLAYING (state 0x%x)\n",
                (unsigned int)source_state);
        result = 11;
        goto cleanup;
    }

    fprintf(stderr, "OpenAL source entered AL_PLAYING successfully\n");
    /* Playback state is verified; audible output still requires listening on hardware. */
    SDL_Delay(550);

cleanup:
    if (context_current) {
        if (source != 0) {
            alSourceStop(source);
            alDeleteSources(1, &source);
            if (check_al_error("source cleanup") != 0) result = result ? result : 12;
        }
        if (buffer != 0) {
            alDeleteBuffers(1, &buffer);
            if (check_al_error("buffer cleanup") != 0) result = result ? result : 13;
        }
        alcMakeContextCurrent(NULL);
    }
    if (context) alcDestroyContext(context);
    if (device) alcCloseDevice(device);
    SDL_Quit();
    return result;
}
