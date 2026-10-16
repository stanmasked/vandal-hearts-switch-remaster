/* Combined native software framebuffer plus PS1 SEQ/VAB/SPU -> audout.
 * Plays locally supplied, user-owned music.seq/.vh/.vb from SD; in their
 * absence it renders generated fixture notes. Original copyrighted data
 * is NOT embedded. Audibility and real game logic remain unverified.
 */
#include <switch.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "game_renderer.h"
#include "game_state.h"
#include "platform_input.h"
#include "vh_audio_assets.h"
#include "vh_audio_resample.h"
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#define WIDTH 1280
#define HEIGHT 720
#define GRID_COLS 8
#define GRID_ROWS 6
#define CELL 76
#define GRID_X 340
#define GRID_Y 108
#define AUDIO_PAGE_BYTES 0x1000u
#define LOCAL_AUDIO_DIR "sdmc:/switch/vandal-hearts-remake/audio"

/* The audio service's buffer_size describes a FULL 4-KiB page, not merely
 * the number of valid PCM frames. Keep the allocation exactly that large. */
static int16_t audio_page[AUDIO_PAGE_BYTES / sizeof(int16_t)]
    __attribute__((aligned(0x1000)));
static Thread sound_thread;
static atomic_bool audio_stop;
static atomic_int audio_fault;
static int audio_active;
static int using_user_files;

/* Permanent storage: no malloc/free or file reads in the audout worker. */
static VhAudioAssets user_assets;
static VhNativeVab synthetic_bank;
static VhNativeSeq seq;
static VhNativeSpu synth;
static VhAudioResample resampler;
static uint8_t fixture_vh[32u + 128u * 16u + 512u + 512u];
static uint8_t fixture_vb[48];
static int16_t fixture_pcm[56];
static int16_t in_44100[VH_AUDIO_BLOCK_FRAMES * 2u];

static const uint8_t fixture_seq[] = {
    'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7, 0,0xb0,7,127, 0,0xb0,10,64,
    0,0x90,60,110, 0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f,
};
static const uint8_t fixture_vag[32] = {
    0x02,0x04,0x22,0x22,0x22,0x22,0x22,0x22,
    0x22,0x22,0x22,0x22,0x22,0x22,0x22,0x22,
    0x02,0x03,0xee,0xee,0xee,0xee,0xee,0xee,
    0xee,0xee,0xee,0xee,0xee,0xee,0xee,0xee,
};

static int prepare_synthetic(void) {
    memset(fixture_vh, 0, sizeof(fixture_vh));
    memset(fixture_vb, 0, sizeof(fixture_vb));
    memcpy(fixture_vh, "pBAV", 4);
    fixture_vh[18] = 8; /* programs up to #7 */
    fixture_vh[20] = 1; /* one tone */
    fixture_vh[22] = 1; /* one VAG */
    fixture_vh[24] = 127;
    const size_t p = 32u + 7u*16u;
    fixture_vh[p] = 1;
    fixture_vh[p+1] = 127;
    fixture_vh[p+4] = 64;
    const size_t t = 32u + 128u*16u;
    fixture_vh[t+1] = 4; /* music tone routes to STUDIO_C send */
    fixture_vh[t+2] = 127;
    fixture_vh[t+3] = 64;
    fixture_vh[t+4] = 60;
    fixture_vh[t+6] = 40;
    fixture_vh[t+7] = 100;
    fixture_vh[t+16] = 15;
    fixture_vh[t+20] = 7; /* parent */
    fixture_vh[t+22] = 1; /* VAG ID */
    fixture_vh[t+512] = 2; /* VAG zero: 16 bytes */
    fixture_vh[t+514] = 4; /* VAG one: 32 bytes */
    memcpy(fixture_vb + 16, fixture_vag, sizeof(fixture_vag));
    if (vh_native_vab_load(
        &synthetic_bank, fixture_vh, sizeof(fixture_vh),
        fixture_vb, sizeof(fixture_vb), fixture_pcm, 56))
        return -1;
    return vh_native_seq_init(&seq, fixture_seq, sizeof(fixture_seq),
                              &synth, vh_native_vab_resolve,
                              &synthetic_bank, 0);
}

static int prepare_music(int *using_user_files) {
    vh_native_spu_reset(&synth);
    if (vh_native_spu_set_interpolation(&synth, VH_SPU_GAUSSIAN) ||
        vh_native_spu_set_reverb(&synth, 1, 0.5f))
        return -1;
    vh_audio_resample_reset(&resampler);
    const int result = vh_audio_assets_load(&user_assets, LOCAL_AUDIO_DIR);
    if (result == VH_AUDIO_ASSET_ERROR) return -1;
    *using_user_files = result == VH_AUDIO_ASSET_OK;
    if (*using_user_files)
        return vh_native_seq_init(
            &seq, user_assets.seq, user_assets.seq_size, &synth,
            vh_native_vab_resolve, &user_assets.bank, 0);
    return prepare_synthetic();
}


static void audio_worker(void *unused) {
    (void)unused;
    AudioOutBuffer desc = {0};
    desc.buffer = audio_page;
    desc.buffer_size = sizeof(audio_page);
    while (!atomic_load(&audio_stop)) {
        if (vh_native_seq_advance_block(&seq) < 0) {
            atomic_store(&audio_fault, 1);
            break;
        }
        vh_native_spu_render(&synth, in_44100, VH_AUDIO_BLOCK_FRAMES);
        const size_t count = vh_audio_resample_process(
            &resampler, in_44100, VH_AUDIO_BLOCK_FRAMES, audio_page,
            VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if (!count || count * 2u * sizeof(int16_t) > desc.buffer_size) {
            atomic_store(&audio_fault, 2);
            break;
        }
        desc.data_size = count * 2u * sizeof(int16_t);
        AudioOutBuffer *released = NULL;
        if (R_FAILED(audoutPlayBuffer(&desc, &released))) {
            atomic_store(&audio_fault, 3);
            break;
        }
    }
}

static int start_native_audio(void) {
    Result result = audoutInitialize();
    if (R_FAILED(result)) return 0;
    if (audoutGetSampleRate() != VH_NATIVE_AUDOUT_RATE ||
        audoutGetChannelCount() != 2 ||
        audoutGetPcmFormat() != PcmFormat_Int16) {
        audoutExit();
        return 0;
    }
    result = audoutStartAudioOut();
    if (R_FAILED(result)) {
        audoutExit();
        return 0;
    }
    atomic_store(&audio_stop, false);
    atomic_store(&audio_fault, 0);
    result = threadCreate(&sound_thread, audio_worker, NULL, NULL,
                          16 * 1024, 0x2c, -2);
    if (R_FAILED(result)) {
        audoutStopAudioOut();
        audoutExit();
        return 0;
    }
    result = threadStart(&sound_thread);
    if (R_FAILED(result)) {
        threadClose(&sound_thread);
        audoutStopAudioOut();
        audoutExit();
        return 0;
    }
    return 1;
}

static void stop_native_audio(void) {
    if (!audio_active) return;
    atomic_store(&audio_stop, true);
    (void)threadWaitForExit(&sound_thread);
    threadClose(&sound_thread);
    audoutStopAudioOut();
    audoutExit();
}

static void paint(VhCanvas *canvas, const VhGameState *state,
                  uint32_t frame) {
    const uint32_t bg = RGBA8_MAXALPHA(17, 23, 39);
    const uint32_t grid = RGBA8_MAXALPHA(83, 100, 119);
    const uint32_t tile = RGBA8_MAXALPHA(38, 54, 75);
    const uint32_t hero = RGBA8_MAXALPHA(86, 190, 244);
    const uint32_t enemy = RGBA8_MAXALPHA(235, 89, 98);
    const uint32_t cursor = RGBA8_MAXALPHA(255, 219, 102);
    const uint32_t sound_ok = RGBA8_MAXALPHA(60, 211, 138);
    const uint32_t sound_fail = RGBA8_MAXALPHA(250, 108, 90);

    vh_canvas_fill_rect(canvas, 0, 0, WIDTH, HEIGHT, bg);
    for (int y = 0; y < GRID_ROWS; ++y) {
        for (int x = 0; x < GRID_COLS; ++x) {
            const int px = GRID_X + x * CELL;
            const int py = GRID_Y + y * CELL;
            const VhTilePalette palette = {
                ((x + y) & 1) ? tile : RGBA8_MAXALPHA(48, 63, 84),
                grid
            };
            vh_render_grid_tile(canvas, px, py, CELL, palette);
            if (x == state->hero_x && y == state->hero_y) {
                vh_canvas_fill_rect(canvas, px + 22, py + 22, 32, 32, hero);
            }
            if (x == state->enemy_x && y == state->enemy_y) {
                vh_canvas_fill_rect(canvas, px + 24, py + 24, 28, 28, enemy);
            }
            if (x == state->cursor_x && y == state->cursor_y) {
                vh_canvas_draw_rect_outline(canvas, px + 5, py + 5,
                                            CELL - 10, CELL - 10, cursor);
            }
        }
    }
    const int healthy = audio_active && atomic_load(&audio_fault) == 0;
    /* Keep status clear of NeXium's top-left performance overlay. */
    vh_canvas_fill_rect(canvas, 1000, 150, 130, 52,
                        healthy ? sound_ok : sound_fail);
    /* Small source marker: bright = local user files; muted = fixture.
     * This is source selection evidence, NOT a sampled-audio recording. */
    vh_canvas_fill_rect(canvas, 1000, 219, 130, 18,
                        using_user_files ? sound_ok : grid);
    /* Animated heartbeat proves video continues while audout worker runs. */
    vh_canvas_fill_rect(canvas, 70, 610, 800, 14, grid);
    vh_canvas_fill_rect(canvas, 70, 610, 20 + (int)(frame % 780u), 14, hero);
}

int main(void) {
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    Framebuffer framebuffer;
    Result rc = framebufferCreate(&framebuffer, nwindowGetDefault(),
                                  WIDTH, HEIGHT, PIXEL_FORMAT_RGBA_8888, 2);
    if (R_FAILED(rc)) return 1;
    rc = framebufferMakeLinear(&framebuffer);
    if (R_FAILED(rc)) {
        framebufferClose(&framebuffer);
        return 2;
    }

    /* Validate + decode the complete selected SEQ/VH/VB set before starting
     * the audio worker. Invalid partial sets fail closed, rather than
     * substituting fixture music. Missing all files uses a synthetic bank. */
    const int music_ready = prepare_music(&using_user_files) == 0;
    audio_active = music_ready ? start_native_audio() : 0;
    VhGameState state = {1, 2, 1, 2, 6, 3, 0};
    uint32_t tick = 0;
    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);
        unsigned actions = 0;
        if (buttons_down & HidNpadButton_Left) actions |= VH_INPUT_LEFT;
        if (buttons_down & HidNpadButton_Right) actions |= VH_INPUT_RIGHT;
        if (buttons_down & HidNpadButton_Up) actions |= VH_INPUT_UP;
        if (buttons_down & HidNpadButton_Down) actions |= VH_INPUT_DOWN;
        if (buttons_down & HidNpadButton_A) actions |= VH_INPUT_CONFIRM;
        if (buttons_down & HidNpadButton_B) actions |= VH_INPUT_CANCEL;
        if (buttons_down & HidNpadButton_Plus) actions |= VH_INPUT_QUIT;
        if (vh_process_input(&state, actions, GRID_COLS, GRID_ROWS, 2))
            break;

        u32 stride = 0;
        u32 *pixels = (u32 *)framebufferBegin(&framebuffer, &stride);
        if (pixels) {
            VhCanvas canvas = {pixels, stride / sizeof(u32), WIDTH, HEIGHT};
            paint(&canvas, &state, tick++);
        }
        framebufferEnd(&framebuffer);
    }

    stop_native_audio();
    /* The worker is fully joined before bank PCM can be released. */
    vh_audio_assets_close(&user_assets);
    framebufferClose(&framebuffer);
    return 0;
}
