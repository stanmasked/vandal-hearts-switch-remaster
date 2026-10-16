/* Combined asset-free libnx framebuffer + audout smoke test.
 * Builds separately from the main prototype. Not an original game port.
 * Audio output and controller behavior require device/emulator verification.
 */
#include <switch.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "game_renderer.h"
#include "game_state.h"
#include "platform_input.h"
#include "vh_native_tone.h"

#define WIDTH 1280
#define HEIGHT 720
#define GRID_COLS 8
#define GRID_ROWS 6
#define CELL 76
#define GRID_X 340
#define GRID_Y 108
#define AUDIO_PAGE_BYTES 0x1000u

/* The audio service's buffer_size describes a FULL 4-KiB page, not merely
 * the number of valid PCM frames. Keep the allocation exactly that large. */
static int16_t audio_page[AUDIO_PAGE_BYTES / sizeof(int16_t)]
    __attribute__((aligned(0x1000)));
static Thread sound_thread;
static atomic_bool audio_stop;
static atomic_int audio_fault;
static int audio_active;

static void audio_worker(void *unused) {
    (void)unused;
    VhNativeTone tone = {0, 0};
    AudioOutBuffer desc = {0};
    desc.buffer = audio_page;
    desc.buffer_size = sizeof(audio_page);
    while (!atomic_load(&audio_stop)) {
        if (vh_native_tone_fill(&tone, audio_page, VH_NATIVE_TONE_FRAMES,
                                sizeof(audio_page) /
                                    (VH_NATIVE_TONE_CHANNELS * sizeof(int16_t)))
                != VH_NATIVE_TONE_FRAMES) {
            atomic_store(&audio_fault, 1);
            break;
        }
        desc.data_size = VH_NATIVE_TONE_FRAMES * 2u * sizeof(int16_t);
        AudioOutBuffer *released = NULL;
        if (R_FAILED(audoutPlayBuffer(&desc, &released))) {
            atomic_store(&audio_fault, 2);
            break;
        }
    }
}

static int start_native_audio(void) {
    Result result = audoutInitialize();
    if (R_FAILED(result)) return 0;
    if (audoutGetSampleRate() != VH_NATIVE_TONE_RATE ||
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

    audio_active = start_native_audio();
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
    framebufferClose(&framebuffer);
    return 0;
}
