#include <SDL.h>
#include <stdint.h>
#include <stdio.h>

#include "vh_audio_stream.h"

#define WIDTH 1280
#define HEIGHT 720

/* Native Switch SDL2 streaming probe, using only synthetic square-wave
 * stereo frames. NOT a VAB/SEQ/SPU integration or proof of audible output.
 * The PCM producer runs on the main thread; callback consumes buffered
 * PCM or fills underruns with silence. Device locking protects the ring.
 */
static VhAudioStream pcm_stream;
static SDL_atomic_t callback_count = {0};
static uint32_t test_phase = 0;

static void audio_callback(void *userdata, Uint8 *stream, int length) {
    (void)userdata;
    if (length <= 0) return;
    const size_t frame_bytes = VH_AUDIO_CHANNELS * sizeof(int16_t);
    const size_t frames = (size_t)length / frame_bytes;
    (void)vh_audio_stream_read(&pcm_stream, (int16_t *)(void *)stream, frames);
    if ((size_t)length % frame_bytes) {
        SDL_memset(stream + frames * frame_bytes, 0,
                   (size_t)length - frames * frame_bytes);
    }
    SDL_AtomicAdd(&callback_count, 1);
}

static void generate_synthetic_stereo(int16_t *out) {
    for (size_t i = 0; i < VH_AUDIO_BLOCK_FRAMES; ++i) {
        /* 441 Hz square wave, generated at 44.1 kHz (100 frames/cycle).
         * Different amplitudes test correct left/right sample ordering.
         */
        const int16_t sample = ((test_phase++ % 100u) < 50u) ? 5500 : -5500;
        out[i * VH_AUDIO_CHANNELS] = sample;
        out[i * VH_AUDIO_CHANNELS + 1] = (int16_t)(sample / 2);
    }
}

static void pump_synthetic_audio(SDL_AudioDeviceID device) {
    int16_t block[VH_AUDIO_BLOCK_FRAMES * VH_AUDIO_CHANNELS];
    /* Do not make or decode PCM in the audio callback. Keep about 2048
     * frames (~46ms) ready using short locks for producer ring writes.
     */
    for (int i = 0; i < 5; ++i) {
        SDL_LockAudioDevice(device);
        const size_t queued = vh_audio_stream_queued(&pcm_stream);
        SDL_UnlockAudioDevice(device);
        if (queued >= 2048u) break;
        generate_synthetic_stereo(block);
        SDL_LockAudioDevice(device);
        (void)vh_audio_stream_write(&pcm_stream, block, VH_AUDIO_BLOCK_FRAMES);
        SDL_UnlockAudioDevice(device);
    }
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
        "SDL2 44.1-kHz stereo PCM stream probe", SDL_WINDOWPOS_CENTERED,
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

    show_status(renderer, 220, 110, 20); /* orange until callback observed */
    vh_audio_stream_reset(&pcm_stream);

    SDL_AudioSpec wanted, obtained;
    SDL_zero(wanted);
    SDL_zero(obtained);
    wanted.freq = VH_AUDIO_SAMPLE_RATE;
    wanted.format = AUDIO_S16SYS;
    wanted.channels = VH_AUDIO_CHANNELS;
    wanted.samples = VH_AUDIO_BLOCK_FRAMES;
    wanted.callback = audio_callback;
    const SDL_AudioDeviceID device = SDL_OpenAudioDevice(
        NULL, 0, &wanted, &obtained, 0 /* reject format/rate changes */);
    if (device == 0) {
        fprintf(stderr, "SDL_OpenAudioDevice failed: %s\n", SDL_GetError());
        show_status(renderer, 210, 35, 45);
        SDL_Delay(12000);
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 3;
    }
    if (obtained.freq != VH_AUDIO_SAMPLE_RATE
        || obtained.channels != VH_AUDIO_CHANNELS
        || obtained.format != AUDIO_S16SYS) {
        fprintf(stderr, "Unexpected SDL audio format (needs 44.1k/S16/stereo)\n");
        SDL_CloseAudioDevice(device);
        show_status(renderer, 210, 35, 45);
        SDL_Delay(12000);
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }
    fprintf(stderr, "PCM ring opened: %d Hz, %u channels, %u callback frames\n",
            obtained.freq, (unsigned)obtained.channels, (unsigned)obtained.samples);

    pump_synthetic_audio(device);
    SDL_PauseAudioDevice(device, 0);
    for (int i = 0; i < 400; ++i) {
        pump_synthetic_audio(device);
        SDL_Delay(5);
    }

    const int callbacks = SDL_AtomicGet(&callback_count);
    if (callbacks > 0) {
        fprintf(stderr, "SDL PCM callbacks observed: %d (audible output unverified)\n",
                callbacks);
        show_status(renderer, 20, 180, 70);
    } else {
        fprintf(stderr, "No PCM callbacks observed (audio output unverified)\n");
        show_status(renderer, 230, 150, 20);
    }

    /* Keep pumping so callbacks don't underrun while status is visible. */
    for (int i = 0; i < 2400; ++i) {
        pump_synthetic_audio(device);
        SDL_Delay(5);
    }
    SDL_PauseAudioDevice(device, 1);
    SDL_LockAudioDevice(device);
    fprintf(stderr, "PCM diagnostics: queued=%u underrun=%llu overflow=%llu\n",
            (unsigned)vh_audio_stream_queued(&pcm_stream),
            (unsigned long long)pcm_stream.underrun_frames,
            (unsigned long long)pcm_stream.overrun_frames);
    SDL_UnlockAudioDevice(device);

    SDL_CloseAudioDevice(device);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return callbacks > 0 ? 0 : 4;
}
