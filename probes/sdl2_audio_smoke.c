#include <SDL.h>
#include <stdio.h>
#include <stdint.h>

#define WIDTH 1280
#define HEIGHT 720
#define SAMPLE_RATE 22050

static volatile uint32_t callback_count = 0;
static uint32_t phase = 0;

static void audio_callback(void *userdata, Uint8 *stream, int length) {
    (void)userdata;
    int16_t *samples = (int16_t *)stream;
    const int count = length / (int)sizeof(*samples);
    for (int i = 0; i < count; ++i) {
        samples[i] = ((phase++ % 50u) < 25u) ? 5000 : -5000;
    }
    callback_count++;
}

static void show_status(SDL_Renderer *renderer, Uint8 r, Uint8 g, Uint8 b) {
    SDL_SetRenderDrawColor(renderer, r, g, b, 255);
    SDL_RenderClear(renderer);
    SDL_RenderPresent(renderer);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO) != 0) {
        fprintf(stderr, "SDL_Init failed: %s\n", SDL_GetError());
        return 1;
    }

    SDL_Window *window = SDL_CreateWindow(
        "SDL2 audio feasibility probe", SDL_WINDOWPOS_CENTERED,
        SDL_WINDOWPOS_CENTERED, WIDTH, HEIGHT, SDL_WINDOW_SHOWN);
    SDL_Renderer *renderer = window
        ? SDL_CreateRenderer(window, -1, SDL_RENDERER_SOFTWARE) : NULL;
    if (!window || !renderer) {
        fprintf(stderr, "SDL display setup failed: %s\n", SDL_GetError());
        if (renderer) SDL_DestroyRenderer(renderer);
        if (window) SDL_DestroyWindow(window);
        SDL_Quit();
        return 2;
    }

    show_status(renderer, 220, 110, 20); /* orange: audio not verified yet */

    SDL_AudioSpec wanted;
    SDL_AudioSpec obtained;
    SDL_zero(wanted);
    SDL_zero(obtained);
    wanted.freq = SAMPLE_RATE;
    wanted.format = AUDIO_S16SYS;
    wanted.channels = 1;
    wanted.samples = 512;
    wanted.callback = audio_callback;

    SDL_AudioDeviceID device = SDL_OpenAudioDevice(NULL, 0, &wanted, &obtained, 0);
    if (device == 0) {
        fprintf(stderr, "SDL_OpenAudioDevice failed: %s\n", SDL_GetError());
        show_status(renderer, 210, 35, 45); /* red: device could not open */
        SDL_Delay(12000);
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 3;
    }

    fprintf(stderr, "SDL audio device opened: freq=%d channels=%u samples=%u\n",
            obtained.freq, (unsigned int)obtained.channels,
            (unsigned int)obtained.samples);
    SDL_PauseAudioDevice(device, 0);
    SDL_Delay(2000);

    const uint32_t callbacks = callback_count;
    if (callbacks > 0) {
        fprintf(stderr, "SDL audio callback observed %u times; audible output is not verified\n",
                (unsigned int)callbacks);
        show_status(renderer, 20, 180, 70); /* green: callback executed */
    } else {
        fprintf(stderr, "SDL audio device opened, but callback was not observed\n");
        show_status(renderer, 230, 150, 20); /* orange: inconclusive */
    }

    SDL_Delay(12000);
    SDL_PauseAudioDevice(device, 1);
    SDL_CloseAudioDevice(device);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return callbacks > 0 ? 0 : 4;
}
