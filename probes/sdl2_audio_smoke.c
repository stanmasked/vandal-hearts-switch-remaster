#include <SDL.h>
#include <stdint.h>
#include <stdio.h>

#include "vh_audio_stream.h"
#include "vh_native_spu.h"
#include "vh_spu_adpcm.h"

#define WIDTH 1280
#define HEIGHT 720

/* Native Switch SDL2 streaming probe, using only synthetic square-wave
 * stereo frames. NOT a VAB/SEQ/SPU integration or proof of audible output.
 * The PCM producer runs on the main thread; callback consumes buffered
 * PCM or fills underruns with silence. Device locking protects the ring.
 */
static VhAudioStream pcm_stream;
static VhNativeSpu native_spu;
static int16_t decoded_vag[VH_SPU_ADPCM_BLOCK_FRAMES * 2u];
static SDL_atomic_t callback_count = {0};


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

/* Synthetic, headerless PS1 VAG: two 28-sample ADPCM blocks, one
 * positive and one negative. The second block flags end+repeat.
 * No game VAG, SEQ or VAB files are included or loaded.
 */
static const uint8_t synthetic_vag[32] = {
    0x02, 0x04, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22,
    0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22, 0x22,
    0x02, 0x03, 0xee, 0xee, 0xee, 0xee, 0xee, 0xee,
    0xee, 0xee, 0xee, 0xee, 0xee, 0xee, 0xee, 0xee,
};

static int init_synthetic_spu(void) {
    VhSpuAdpcmInfo info;
    if (vh_spu_adpcm_decode(
        synthetic_vag, sizeof(synthetic_vag), decoded_vag,
        sizeof(decoded_vag) / sizeof(decoded_vag[0]), &info) != 0)
        return -1;
    if (info.frames != 56 || info.loop_start_frame != 0 ||
        info.loop_end_frame != 56) return -1;
    vh_native_spu_reset(&native_spu);
    const int slot = vh_native_spu_allocate_slot(&native_spu);
    if (slot < 0) return -1;
    return vh_native_spu_note_on(
        &native_spu, (unsigned)slot, decoded_vag, info.frames,
        info.loop_start_frame, info.loop_end_frame, 0x1000,
        0x000f, 0, 0.6f, 0.3f);
}

static void pump_synthetic_audio(SDL_AudioDeviceID device) {
    int16_t block[VH_AUDIO_BLOCK_FRAMES * VH_AUDIO_CHANNELS];
    /* Audio rendering is on the producer thread OUTSIDE the device lock:
     * only enqueueing and queue-length inspection need SDL synchronization.
     */
    for (int i = 0; i < 5; ++i) {
        SDL_LockAudioDevice(device);
        const size_t queued = vh_audio_stream_queued(&pcm_stream);
        SDL_UnlockAudioDevice(device);
        if (queued >= 2048u) break;
        vh_native_spu_render(&native_spu, block, VH_AUDIO_BLOCK_FRAMES);
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
    if (init_synthetic_spu() != 0) {
        fprintf(stderr, "Synthetic VAG decode/SPU init failed\\n");
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 6;
    }

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
    fprintf(stderr, "Native SPU-ADPCM PCM ring opened: %d Hz, %u channels, %u callback frames\n",
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
