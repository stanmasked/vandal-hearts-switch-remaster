#include <SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_stream.h"
#include "vh_native_spu.h"
#include "vh_native_seq.h"
#include "vh_native_vab.h"
#include "vh_audio_assets.h"
#include "vh_spu_adpcm.h"

#define WIDTH 1280
#define HEIGHT 720
/* Copy only user-owned extracted assets to this directory on the SD card. */
#define VH_LOCAL_AUDIO_DIR "sdmc:/switch/vandal-hearts-remake/audio"

/* Native Switch SDL2 streaming probe: tries a local read-only SEQ/VH/VB
 * set, otherwise fabricated fixtures if all files are absent.
 * NOT proof of audible output or correctness against original hardware.
 * The PCM producer runs on the main thread; callback consumes buffered
 * PCM or fills underruns with silence. Device locking protects the ring.
 */
static VhAudioStream pcm_stream;
static VhNativeSpu native_spu;
static VhNativeSeq native_seq;
static int seq_failed = 0;
static VhNativeVab native_bank;
static VhAudioAssets local_assets;
static int using_local_assets = 0;
static int16_t decoded_vag[VH_SPU_ADPCM_BLOCK_FRAMES * 2u];
static uint8_t synthetic_vh[32u + 128u * 16u + 512u + 512u];
static uint8_t synthetic_vb[16u + 32u];
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

/* Valid PS1 pQES single-track synthetic phrase: program 7, one note
 * for 240 ticks (0.25s at PPQN 480), then an EOT after another 240.
 * Infinite looping rekeys the note at each clean FF 2F boundary.
 */
static const uint8_t synthetic_seq[] = {
    'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7, 0,0xb0,7,127, 0,0xb0,10,64,
    0,0x90,60,110, 0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f,
};

static int init_synthetic_seq(void) {
    /* One sparse program (program ID 7), one looping two-block VAG.
     * The VH is fabricated entirely at startup. No game assets.
     */
    memset(synthetic_vh, 0, sizeof(synthetic_vh));
    memset(synthetic_vb, 0, sizeof(synthetic_vb));
    memcpy(synthetic_vh, "pBAV", 4);
    synthetic_vh[18] = 8; /* declared program count includes sparse ID 7 */
    synthetic_vh[20] = 1; /* one tone */
    synthetic_vh[22] = 1; /* one playable VAG */
    synthetic_vh[24] = 127;
    const size_t prog = 32u + 7u * 16u;
    synthetic_vh[prog] = 1;
    synthetic_vh[prog+1] = 127;
    synthetic_vh[prog+4] = 64;
    const size_t tone = 32u + 128u * 16u;
    synthetic_vh[tone+1] = 4; /* music tone's reverb send */
    synthetic_vh[tone+2] = 127;
    synthetic_vh[tone+3] = 64;
    synthetic_vh[tone+4] = 60;
    synthetic_vh[tone+6] = 40;
    synthetic_vh[tone+7] = 100;
    synthetic_vh[tone+16] = 15; /* ADSR1 little endian */
    synthetic_vh[tone+20] = 7;  /* parent program 7 */
    synthetic_vh[tone+22] = 1;  /* VAG index 1 */
    const size_t sizes = tone + 512u;
    synthetic_vh[sizes] = 2;   /* zero entry: 16 bytes */
    synthetic_vh[sizes+2] = 4; /* VAG #1: 32 bytes */
    memcpy(synthetic_vb + 16, synthetic_vag, sizeof(synthetic_vag));
    if (vh_native_vab_load(
            &native_bank, synthetic_vh, sizeof(synthetic_vh),
            synthetic_vb, sizeof(synthetic_vb), decoded_vag,
            sizeof(decoded_vag)/sizeof(decoded_vag[0])) != 0)
        return -1;
    vh_native_spu_reset(&native_spu);
    if (vh_native_spu_set_interpolation(&native_spu, VH_SPU_GAUSSIAN) != 0)
        return -1;
    return vh_native_seq_init(
        &native_seq, synthetic_seq, sizeof(synthetic_seq),
        &native_spu, vh_native_vab_resolve, &native_bank,
        0 /* repeat until probe closes */);
}

/* Never silently replace an invalid user-supplied bank with synthetic
 * audio. Fallback is allowed only when ALL three files are absent.
 * All file reads and SPU-ADPCM decoding finish before audio begins.
 */
static int init_audio_sources(void) {
    const int result = vh_audio_assets_load(
        &local_assets, VH_LOCAL_AUDIO_DIR);
    if (result == VH_AUDIO_ASSET_ERROR) {
        fprintf(stderr,
            "Audio assets incomplete, corrupt or too large; refusing playback\n");
        return -1;
    }
    if (result == VH_AUDIO_ASSET_OK) {
        vh_native_spu_reset(&native_spu);
        if (vh_native_spu_set_interpolation(
                &native_spu, VH_SPU_GAUSSIAN) != 0 ||
            vh_native_seq_init(
                &native_seq, local_assets.seq, local_assets.seq_size,
                &native_spu, vh_native_vab_resolve, &local_assets.bank,
                0 /* repeat until the probe closes */) != 0) {
            vh_audio_assets_close(&local_assets);
            return -1;
        }
        using_local_assets = 1;
        fprintf(stderr,
            "Loaded local user-owned SEQ/VH/VB into memory (read-only)\n");
        return 0;
    }
    using_local_assets = 0;
    fprintf(stderr, "Local audio set absent; using synthetic SEQ/VH/VB\n");
    return init_synthetic_seq();
}

static void close_audio_sources(void) {
    /* Call only after SDL_CloseAudioDevice: borrowed VAG PCM data may
     * still be referenced by queued SPU voices until audio stops.
     */
    vh_audio_assets_close(&local_assets);
    using_local_assets = 0;
}

static void pump_native_audio(SDL_AudioDeviceID device) {
    int16_t block[VH_AUDIO_BLOCK_FRAMES * VH_AUDIO_CHANNELS];
    /* Audio rendering is on the producer thread OUTSIDE the device lock:
     * only enqueueing and queue-length inspection need SDL synchronization.
     */
    for (int i = 0; i < 5; ++i) {
        SDL_LockAudioDevice(device);
        const size_t queued = vh_audio_stream_queued(&pcm_stream);
        SDL_UnlockAudioDevice(device);
        if (queued >= 2048u) break;
        /* Match PC-port ordering: advance SEQ BEFORE rendering the
         * corresponding 512-frame PCM block.
         */
        if (vh_native_seq_advance_block(&native_seq) < 0) {
            seq_failed = 1;
            return;
        }
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
    if (init_audio_sources() != 0) {
        fprintf(stderr, "SEQ/VH/VB/SPU initialization failed\n");
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
        close_audio_sources();
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
        close_audio_sources();
        show_status(renderer, 210, 35, 45);
        SDL_Delay(12000);
        SDL_DestroyRenderer(renderer);
        SDL_DestroyWindow(window);
        SDL_Quit();
        return 5;
    }
    fprintf(stderr, "SEQ + VH/VB -> SPU -> SDL2 (%s): %d Hz, %u channels, %u callback frames\n",
            using_local_assets ? "local files" : "synthetic",
            obtained.freq, (unsigned)obtained.channels, (unsigned)obtained.samples);

    pump_native_audio(device);
    SDL_PauseAudioDevice(device, 0);
    for (int i = 0; i < 400; ++i) {
        pump_native_audio(device);
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
        pump_native_audio(device);
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
    close_audio_sources();
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
    return seq_failed ? 7 : (callbacks > 0 ? 0 : 4);
}
