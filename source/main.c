#include <switch.h>
#include <string.h>
#include <stdio.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

#include "vh_audio_diag_journal.h"
#include "vh_audio_diag_export.h"

#include "game_rules.h"
#include "game_state.h"
#include "game_renderer.h"
#include "platform_input.h"
#include "software_renderer.h"
#include "vh_switch_game_audio.h"
#include "vh_audio_scene_optical.h"

#define FB_WIDTH 1280
#define FB_HEIGHT 720
#define GRID_WIDTH 8
#define GRID_HEIGHT 6
#define MOVE_RANGE 2
#define CELL_SIZE 72
#define GRID_X 352
#define GRID_Y 100

#define COLOR_BG       RGBA8_MAXALPHA(12, 18, 34)
#define COLOR_PANEL    RGBA8_MAXALPHA(24, 34, 54)
#define COLOR_GRID     RGBA8_MAXALPHA(58, 74, 96)
#define COLOR_TILE     RGBA8_MAXALPHA(34, 48, 68)
#define COLOR_TILE_ALT RGBA8_MAXALPHA(39, 54, 75)
#define COLOR_RANGE    RGBA8_MAXALPHA(43, 91, 91)
#define COLOR_HERO     RGBA8_MAXALPHA(86, 190, 244)
#define COLOR_ENEMY    RGBA8_MAXALPHA(235, 89, 98)
#define COLOR_CURSOR   RGBA8_MAXALPHA(255, 219, 102)
#define COLOR_WHITE    RGBA8_MAXALPHA(224, 234, 246)
#define COLOR_MUTED    RGBA8_MAXALPHA(105, 126, 151)

/* Game thread owns the bounded 128-row log. No file operations are
 * performed until AFTER the audout worker has stopped and joined. */
static VhAudioDiagJournal hardware_audio_log;

static void fill_rect(u32 *pixels, u32 stride, int x, int y,
                      int width, int height, u32 color) {
    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    vh_canvas_fill_rect(&canvas, x, y, width, height, color);
}

/* Tiny generated 5x7 font: no copyrighted game fonts or external assets. */
static const u8 FONT_5X7[36][5] = {
    {0x7E,0x11,0x11,0x11,0x7E}, {0x7F,0x49,0x49,0x49,0x36},
    {0x3E,0x41,0x41,0x41,0x22}, {0x7F,0x41,0x41,0x22,0x1C},
    {0x7F,0x49,0x49,0x49,0x41}, {0x7F,0x09,0x09,0x09,0x01},
    {0x3E,0x41,0x49,0x49,0x7A}, {0x7F,0x08,0x08,0x08,0x7F},
    {0x00,0x41,0x7F,0x41,0x00}, {0x20,0x40,0x41,0x3F,0x01},
    {0x7F,0x08,0x14,0x22,0x41}, {0x7F,0x40,0x40,0x40,0x40},
    {0x7F,0x02,0x0C,0x02,0x7F}, {0x7F,0x04,0x08,0x10,0x7F},
    {0x3E,0x41,0x41,0x41,0x3E}, {0x7F,0x09,0x09,0x09,0x06},
    {0x3E,0x41,0x51,0x21,0x5E}, {0x7F,0x09,0x19,0x29,0x46},
    {0x46,0x49,0x49,0x49,0x31}, {0x01,0x01,0x7F,0x01,0x01},
    {0x3F,0x40,0x40,0x40,0x3F}, {0x1F,0x20,0x40,0x20,0x1F},
    {0x3F,0x40,0x38,0x40,0x3F}, {0x63,0x14,0x08,0x14,0x63},
    {0x07,0x08,0x70,0x08,0x07}, {0x61,0x51,0x49,0x45,0x43},
    {0x3E,0x45,0x49,0x51,0x3E}, {0x00,0x42,0x7F,0x40,0x00},
    {0x62,0x51,0x49,0x49,0x46}, {0x22,0x41,0x49,0x49,0x36},
    {0x18,0x14,0x12,0x7F,0x10}, {0x2F,0x49,0x49,0x49,0x31},
    {0x3E,0x49,0x49,0x49,0x32}, {0x01,0x71,0x09,0x05,0x03},
    {0x36,0x49,0x49,0x49,0x36}, {0x26,0x49,0x49,0x49,0x3E}
};

static const u8 *font_glyph(char ch) {
    static const u8 blank[5] = {0,0,0,0,0};
    static const u8 dash[5] = {0,0,0x08,0,0};
    static const u8 plus[5] = {0x08,0x08,0x3E,0x08,0x08};
    if (ch >= 'A' && ch <= 'Z') return FONT_5X7[ch - 'A'];
    if (ch >= '0' && ch <= '9') return FONT_5X7[26 + ch - '0'];
    if (ch == '-') return dash;
    if (ch == '+') return plus;
    return blank;
}

static void draw_text(u32 *pixels, u32 stride, int x, int y,
                      const char *text, u32 color, int scale) {
    for (const char *p = text; *p; p++) {
        if (*p == ' ') {
            x += 6 * scale;
            continue;
        }
        const u8 *glyph = font_glyph(*p);
        for (int col = 0; col < 5; col++) {
            for (int row = 0; row < 7; row++) {
                if (glyph[col] & (1u << row)) {
                    fill_rect(pixels, stride, x + col * scale, y + row * scale,
                              scale, scale, color);
                }
            }
        }
        x += 6 * scale;
    }
}

static void draw_frame(u32 *pixels, u32 stride, int cursor_x, int cursor_y,
                       int hero_x, int hero_y, int enemy_x, int enemy_y,
                       int hero_selected, u32 frame_tick,
                       int audio_status, unsigned bank_warnings,
                       const VhAudioDiagText *diagnostics,
                       int log_active, unsigned log_rows) {
    fill_rect(pixels, stride, 0, 0, FB_WIDTH, FB_HEIGHT, COLOR_BG);

    /* Compact bitmap labels keep the prototype self-contained and asset-free. */
    draw_text(pixels, stride, 72, 28, "VANDAL HEARTS", COLOR_WHITE, 3);
    draw_text(pixels, stride, 72, 59, "TACTICAL PROTOTYPE", COLOR_MUTED, 1);
    draw_text(pixels, stride, 700, 59,
              hero_selected ? "CHOOSE DESTINATION" : "SELECT HERO",
              COLOR_WHITE, 1);
    fill_rect(pixels, stride, 72, 82, FB_WIDTH - 144, 2, COLOR_HERO);

    VhCanvas canvas = {(uint32_t *)pixels, (size_t)stride, FB_WIDTH, FB_HEIGHT};
    for (int y = 0; y < GRID_HEIGHT; y++) {
        for (int x = 0; x < GRID_WIDTH; x++) {
            const int px = GRID_X + x * CELL_SIZE;
            const int py = GRID_Y + y * CELL_SIZE;
            u32 tile = ((x + y) & 1) ? COLOR_TILE_ALT : COLOR_TILE;

            if (hero_selected &&
                vh_manhattan_distance(hero_x, hero_y, x, y) <= MOVE_RANGE &&
                !(x == enemy_x && y == enemy_y)) {
                tile = COLOR_RANGE;
            }

            VhTilePalette palette = {tile, COLOR_GRID};
            vh_render_grid_tile(&canvas, px, py, CELL_SIZE, palette);

            if (x == hero_x && y == hero_y) {
                const int inset = hero_selected ? 13 : 18;
                fill_rect(pixels, stride, px + inset, py + inset, CELL_SIZE - inset * 2,
                          CELL_SIZE - inset * 2, COLOR_HERO);
                fill_rect(pixels, stride, px + CELL_SIZE / 2 - 4, py + 8, 8, 8, COLOR_WHITE);
            }

            if (x == enemy_x && y == enemy_y) {
                fill_rect(pixels, stride, px + 17, py + 17, CELL_SIZE - 34, CELL_SIZE - 34, COLOR_ENEMY);
                fill_rect(pixels, stride, px + 25, py + 25, CELL_SIZE - 50, CELL_SIZE - 50, COLOR_BG);
            }

            if (x == cursor_x && y == cursor_y) {
                fill_rect(pixels, stride, px + 4, py + 4, CELL_SIZE - 8, 4, COLOR_CURSOR);
                fill_rect(pixels, stride, px + 4, py + CELL_SIZE - 8, CELL_SIZE - 8, 4, COLOR_CURSOR);
                fill_rect(pixels, stride, px + 4, py + 4, 4, CELL_SIZE - 8, COLOR_CURSOR);
                fill_rect(pixels, stride, px + CELL_SIZE - 8, py + 4, 4, CELL_SIZE - 8, COLOR_CURSOR);
            }
        }
    }

    fill_rect(pixels, stride, 72, 590, FB_WIDTH - 144, 2, COLOR_GRID);
    fill_rect(pixels, stride, 72, 615, 42, 42, COLOR_HERO);
    fill_rect(pixels, stride, 132, 615, 42, 42, COLOR_ENEMY);
    fill_rect(pixels, stride, 192, 615, 42, 42, COLOR_CURSOR);
    draw_text(pixels, stride, 252, 622, "HERO ENEMY CURSOR", COLOR_WHITE, 1);
    draw_text(pixels, stride, 72, 674, "D-PAD MOVE  A SELECT  B CANCEL  PLUS EXIT", COLOR_MUTED, 1);
    draw_text(pixels, stride, 930, 674, "MINUS AUDIO", COLOR_MUTED, 1);

    /* Diagnostic heartbeat bar: changing length proves the framebuffer is being redrawn. */
    fill_rect(pixels, stride, 1000, 600, 96, 8, COLOR_GRID);
    fill_rect(pixels, stride, 1000, 600, 8 + (int)(frame_tick % 89), 8, COLOR_HERO);
    draw_text(pixels, stride, 1000, 612, "FRAME", COLOR_MUTED, 1);
    draw_text(pixels, stride, 1000, 633,
              audio_status < 0 ? "AUDIO ERROR" :
              audio_status == 0 ? "AUDIO START" :
              audio_status == 2 ? "AUDIO PAUSED" :
              hero_selected ? "MUSIC FOCUS" : "MUSIC FIELD",
              audio_status < 0 ? COLOR_ENEMY : COLOR_MUTED, 1);

    if (audio_status == 1 && bank_warnings) {
        /* A valid user VH may resolve an instrument via a fallback
         * program/range. Warn instead of pretending the timbre matches
         * original PlayStation playback; count can be examined in
         * loader diagnostics and is never a game-thread bank pointer.
         */
        draw_text(pixels, stride, 1000, 650, "VAB FALLBACK",
                  COLOR_CURSOR, 1);
    }

    if (diagnostics) {
        /* Read-only audio test panel, away from the tactical grid.
         * This renders from atomic snapshots only: no audout, bank
         * pointer, mutex, filesystem or music state is accessed. */
        fill_rect(pixels,stride,962,124,292,340,COLOR_PANEL);
        fill_rect(pixels,stride,962,124,292,3,COLOR_CURSOR);
        for (unsigned i=0;i<VH_AUDIO_DIAG_LINES;i++)
            draw_text(pixels,stride,978,144+(int)i*25,
                      diagnostics->line[i],
                      i==0 ? COLOR_CURSOR:COLOR_WHITE,1);
        draw_text(pixels,stride,978,414,
                  log_active ? "Y STOP LOG" : "Y START LOG",
                  log_active ? COLOR_CURSOR : COLOR_MUTED,1);
        char rows[32];
        snprintf(rows,sizeof rows,"LOG ROWS %u",log_rows);
        draw_text(pixels,stride,978,436,rows,COLOR_MUTED,1);
        draw_text(pixels,stride,978,456,"MINUS CLOSE",COLOR_MUTED,1);
    }

    /* Small status indicator changes color while the unit is selected. */
    fill_rect(pixels, stride, FB_WIDTH - 116, 42, 44, 44,
              hero_selected ? COLOR_CURSOR : COLOR_HERO);
}

/* Only ap pname/message processing (main thread) reads libnx focus.
 * Callback publishes an atomic status; it never invokes audout or
 * interacts with SPU state from this thread.
 */
static void on_music_applet_event(AppletHookType event, void *context) {
    (void)context;
    const int in_focus =
        appletGetFocusState() == AppletFocusState_InFocus;
    if (event == AppletHookType_OnResume)
        vh_switch_game_audio_on_resume(in_focus);
    else if (event == AppletHookType_OnFocusState)
        vh_switch_game_audio_set_focus(in_focus);
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    Framebuffer fb;
    Result rc = framebufferCreate(&fb, nwindowGetDefault(), FB_WIDTH, FB_HEIGHT,
                                  PIXEL_FORMAT_RGBA_8888, 2);
    if (R_FAILED(rc)) return 1;

    rc = framebufferMakeLinear(&fb);
    if (R_FAILED(rc)) {
        framebufferClose(&fb);
        return 1;
    }

    VhGameState state = {1, 2, 1, 2, 6, 3, 0};
    /* Music is rendered by a dedicated audout thread; startup failure
     * must not prevent the tactical prototype from remaining playable.
     * No audout blocking occurs in this input/framebuffer loop.
     */
    const int audio_started = vh_switch_game_audio_start(
        vh_game_music_for_state(&state)) == 0;
    AppletHookCookie focus_hook = {0};
    int resume_message_enabled = 0;
    if (audio_started) {
        /* Only full Application applets support this libnx setting.
         * HOME/sleep may suspend all threads before a focus callback,
         * so request an explicit OnResume notification when supported.
         */
        if (appletGetAppletType() == AppletType_Application)
            resume_message_enabled =
                R_SUCCEEDED(appletSetRestartMessageEnabled(true));
        vh_switch_game_audio_set_focus(
            appletGetFocusState() == AppletFocusState_InFocus);
        appletHook(&focus_hook, on_music_applet_event, NULL);
    }
    u32 frame_tick = 0;
    int audio_diagnostics_visible = 0;
    int optical_receipt_requested = 0; /* held X while pressing Plus */
    int log_active = 0, log_has_samples = 0;
    const uint64_t session_start_tick=armGetSystemTick();
    vh_audio_diag_journal_reset(&hardware_audio_log);

    while (appletMainLoop()) {
        /* Some libnx launch modes suspend main before issuing focus
         * callbacks. This refresh handles the first frame after resume.
         */
        if (audio_started)
            vh_switch_game_audio_set_focus(
                appletGetFocusState() == AppletFocusState_InFocus);
        padUpdate(&pad);
        const u64 buttons_down = padGetButtonsDown(&pad);
        /* Opt-in diagnostic only. A normal Plus exit is unchanged.
         * Rendering occurs after joining audout and SD export, not
         * in any game/audio callback. */
        if ((buttons_down & HidNpadButton_Plus) &&
            (padGetButtons(&pad) & HidNpadButton_X))
            optical_receipt_requested = 1;
        if (buttons_down & HidNpadButton_Minus)
            audio_diagnostics_visible = !audio_diagnostics_visible;
        const uint64_t elapsed_ms=armTicksToNs(
            armGetSystemTick()-session_start_tick)/UINT64_C(1000000);
        if (audio_diagnostics_visible && (buttons_down & HidNpadButton_Y)) {
            /* Recording is opt-in. Toggling Y pauses/resumes the same
             * bounded session log, never files a write on this path. */
            log_active=!log_active;
            if (log_active && !log_has_samples)
                vh_audio_diag_journal_reset(&hardware_audio_log);
            log_has_samples=1;
        }
        if (log_active) {
            VhAudioDiagnostics sample={0};
            if (audio_started)
                vh_switch_game_audio_diagnostics(&sample);
            else
                sample.status=-1;
            (void)vh_audio_diag_journal_sample(
                &hardware_audio_log,elapsed_ms,&sample);
        }

        unsigned int actions = 0;
        if (buttons_down & HidNpadButton_Left)  actions |= VH_INPUT_LEFT;
        if (buttons_down & HidNpadButton_Right) actions |= VH_INPUT_RIGHT;
        if (buttons_down & HidNpadButton_Up)    actions |= VH_INPUT_UP;
        if (buttons_down & HidNpadButton_Down)  actions |= VH_INPUT_DOWN;
        if (buttons_down & HidNpadButton_A)     actions |= VH_INPUT_CONFIRM;
        if (buttons_down & HidNpadButton_B)     actions |= VH_INPUT_CANCEL;
        if (buttons_down & HidNpadButton_Plus)  actions |= VH_INPUT_QUIT;

        /* Input receipt is recorded in the SAME guest monotonic clock
         * as the audio worker, before game rules process this press.
         * It does not timestamp the HID driver or emulated host key. */
        const uint64_t input_observed_ns =
            (buttons_down & (HidNpadButton_A | HidNpadButton_B))
            ? armTicksToNs(armGetSystemTick()) : 0;
        const unsigned previous_music = vh_game_music_for_state(&state);
        if (vh_process_input(&state, actions, GRID_WIDTH, GRID_HEIGHT, MOVE_RANGE))
            break;
        const unsigned next_music = vh_game_music_for_state(&state);
        if (audio_started && previous_music != next_music)
            vh_switch_game_audio_post_at(next_music,
                input_observed_ns ? input_observed_ns
                                  : armTicksToNs(armGetSystemTick()));

        u32 stride_bytes = 0;
        u32 *pixels = (u32 *)framebufferBegin(&fb, &stride_bytes);
        if (pixels) {
            const u32 stride_pixels = stride_bytes / sizeof(u32);
            VhAudioDiagnostics audio_snapshot={0};
            VhAudioDiagText audio_lines={0};
            const VhAudioDiagText *overlay=NULL;
            if (audio_diagnostics_visible) {
                if (audio_started)
                    vh_switch_game_audio_diagnostics(&audio_snapshot);
                else
                    audio_snapshot.status=-1;
                if (!vh_audio_diag_format(&audio_snapshot,&audio_lines))
                    overlay=&audio_lines;
            }
            draw_frame(pixels, stride_pixels, state.cursor_x, state.cursor_y,
                       state.hero_x, state.hero_y, state.enemy_x, state.enemy_y,
                       state.hero_selected, frame_tick++,
                       audio_started ? vh_switch_game_audio_status() : -1,
                       audio_started ? vh_switch_game_audio_bank_warnings() : 0u,
                       overlay,log_active,hardware_audio_log.count);
        }
        framebufferEnd(&fb);
    }

    /* Wait for the audio producer only once during shutdown, never
     * during a gameplay/framebuffer frame.
     */
    int export_status=0;
    if (audio_started) {
        appletUnhook(&focus_hook);
        vh_switch_game_audio_stop();
        /* All scene event slots are immutable after joining the audio
         * producer. No SD I/O, malloc or CSV formatting was performed
         * in the game or audio loops. Guest stderr can be absent in
         * NeXium; SD CSV is the independent recovery channel. */
        (void)vh_switch_game_audio_trace_dump(stderr);
        /* Separate queue observations, not part of the 64-slot scene
         * witness. Guest stderr visibility depends on the emulator. */
        if(fputs("VH_AUDOUT_QUEUE_TELEMETRY_BEGIN\n",stderr)>=0) {
            const int queue_rows=vh_switch_game_audio_queue_dump(stderr);
            fprintf(stderr,"VH_AUDOUT_QUEUE_TELEMETRY_END,rows=%d\n",
                    queue_rows);
        }
        (void)mkdir("sdmc:/switch",0777);
        (void)mkdir(VH_SCENE_TRACE_SD_DIRECTORY,0777);
        char scene_path[VH_SCENE_TRACE_EXPORT_PATH_CAP];
        const VhSceneExportResult saved=vh_switch_game_audio_trace_export(
            scene_path,sizeof scene_path);
        if(saved!=VH_SCENE_EXPORT_OK) {
            fprintf(stderr,"audio scene trace SD export failed: %d\n",
                    (int)saved);
            export_status=2;
        }
        char audout_path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
        const VhAudoutQueueExportResult audout_saved=
            vh_switch_game_audio_queue_export(
                audout_path,sizeof audout_path);
        /* Always record the API result as a distinct, bounded guest
         * receipt. This probes same-process visibility: the native
         * exporter can report success while NeXium's host SD mirror
         * has no matching file. Neither case proves audible output.
         * Never fabricate the missing CSV. */
        struct stat audout_stat;
        const int audout_seen=audout_saved==VH_AUDOUT_QUEUE_EXPORT_OK
            && stat(audout_path,&audout_stat)==0
            && S_ISREG(audout_stat.st_mode);
        const int receipt_fd=open(
            "sdmc:/switch/vandal-hearts-remake/audio-audout-export-result.txt",
            O_WRONLY|O_CREAT|O_EXCL,0600);
        if(receipt_fd>=0) {
            char message[160];
            const int n=snprintf(message,sizeof message,
                "export_status=%d\npath_present=%u\nfile_size=%llu\n",
                (int)audout_saved,audout_seen?1u:0u,
                audout_seen ? (unsigned long long)audout_stat.st_size:0ull);
            if(n>0 && (size_t)n<sizeof message)
                (void)write(receipt_fd,message,(size_t)n);
            (void)close(receipt_fd);
        }
        if(audout_saved!=VH_AUDOUT_QUEUE_EXPORT_OK || !audout_seen) {
            fprintf(stderr,
                "audout queue telemetry SD export failed: %d, path_present=%d\n",
                (int)audout_saved,audout_seen);
            export_status=2;
        }
        /* Stage 272 is a SEPARATE CSV: the original queue CSV schema
         * and its receipt remain untouched. Only after audout join. */
        char latency_path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
        const VhAudoutQueueExportResult latency_saved=
            vh_switch_game_audio_latency_export(
                latency_path,sizeof latency_path);
        struct stat latency_stat;
        const int latency_seen=latency_saved==VH_AUDOUT_QUEUE_EXPORT_OK
            && stat(latency_path,&latency_stat)==0
            && S_ISREG(latency_stat.st_mode);
        const int latency_receipt_fd=open(
            "sdmc:/switch/vandal-hearts-remake/audio-audout-latency-export-result.txt",
            O_WRONLY|O_CREAT|O_EXCL,0600);
        if(latency_receipt_fd>=0) {
            char message[160];
            const int n=snprintf(message,sizeof message,
                "export_status=%d\npath_present=%u\nfile_size=%llu\n",
                (int)latency_saved,latency_seen?1u:0u,
                latency_seen ? (unsigned long long)latency_stat.st_size:0ull);
            if(n>0 && (size_t)n<sizeof message)
                (void)write(latency_receipt_fd,message,(size_t)n);
            (void)close(latency_receipt_fd);
        }
        if(latency_saved!=VH_AUDOUT_QUEUE_EXPORT_OK || !latency_seen) {
            fprintf(stderr,
                "audout latency histogram SD export failed: %d, path_present=%d\n",
                (int)latency_saved,latency_seen);
            export_status=2;
        }
        /* Independent guest-monotonic epoch for correlating audout
         * seconds with INPUT/POST timestamps. Never host wall-clock. */
        char clock_path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
        const VhAudoutQueueExportResult clock_saved=
            vh_switch_game_audio_clock_export(clock_path,sizeof clock_path);
        struct stat clock_stat;
        const int clock_seen=clock_saved==VH_AUDOUT_QUEUE_EXPORT_OK
            && stat(clock_path,&clock_stat)==0
            && S_ISREG(clock_stat.st_mode);
        const int clock_receipt_fd=open(
            "sdmc:/switch/vandal-hearts-remake/audio-audout-clock-export-result.txt",
            O_WRONLY|O_CREAT|O_EXCL,0600);
        if(clock_receipt_fd>=0) {
            char message[160];
            const int n=snprintf(message,sizeof message,
                "export_status=%d\npath_present=%u\nfile_size=%llu\n",
                (int)clock_saved,clock_seen?1u:0u,
                clock_seen ? (unsigned long long)clock_stat.st_size:0ull);
            if(n>0 && (size_t)n<sizeof message)
                (void)write(clock_receipt_fd,message,(size_t)n);
            (void)close(clock_receipt_fd);
        }
        if(clock_saved!=VH_AUDOUT_QUEUE_EXPORT_OK || !clock_seen) {
            fprintf(stderr,
                "audout guest clock origin SD export failed: %d, path_present=%d\n",
                (int)clock_saved,clock_seen);
            export_status=2;
        }
        /* Stage274 bounded timestamp evidence, after joining audio owner.
         * Never overwrite the stage269/272/273 original guest SD CSVs. */
        char slow_path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
        const VhAudoutQueueExportResult slow_saved=
            vh_switch_game_audio_slow_export(slow_path,sizeof slow_path);
        struct stat slow_stat;
        const int slow_seen=slow_saved==VH_AUDOUT_QUEUE_EXPORT_OK
            && stat(slow_path,&slow_stat)==0 && S_ISREG(slow_stat.st_mode);
        const int slow_receipt_fd=open(
            "sdmc:/switch/vandal-hearts-remake/audio-audout-slow-export-result.txt",
            O_WRONLY|O_CREAT|O_EXCL,0600);
        if(slow_receipt_fd>=0) {
            char message[160];
            const int n=snprintf(message,sizeof message,
                "export_status=%d\npath_present=%u\nfile_size=%llu\n",
                (int)slow_saved,slow_seen?1u:0u,
                slow_seen ? (unsigned long long)slow_stat.st_size:0ull);
            if(n>0 && (size_t)n<sizeof message)
                (void)write(slow_receipt_fd,message,(size_t)n);
            (void)close(slow_receipt_fd);
        }
        if(slow_saved!=VH_AUDOUT_QUEUE_EXPORT_OK || !slow_seen) {
            fprintf(stderr,
                "audout slow-call SD export failed: %d, path_present=%d\n",
                (int)slow_saved,slow_seen);
            export_status=2;
        }
        /* Stage289: a separate numbered, read-back verified record of
         * existing 1/16 pre-submit service probes; no new hot-path IO.
         * Never confuse the service count with DAC/scheduler state. */
        char probe_path[VH_AUDOUT_QUEUE_EXPORT_PATH_CAP];
        const VhAudoutQueueExportResult probe_saved=
            vh_switch_game_audio_probe_export(probe_path,sizeof probe_path);
        struct stat probe_stat;
        const int probe_seen=probe_saved==VH_AUDOUT_QUEUE_EXPORT_OK
            && stat(probe_path,&probe_stat)==0 && S_ISREG(probe_stat.st_mode);
        const int probe_receipt_fd=open(
            "sdmc:/switch/vandal-hearts-remake/audio-audout-probe-export-result.txt",
            O_WRONLY|O_CREAT|O_EXCL,0600);
        if(probe_receipt_fd>=0) {
            char message[160];
            const int n=snprintf(message,sizeof message,
                "export_status=%d\\npath_present=%u\\nfile_size=%llu\\n",
                (int)probe_saved,probe_seen?1u:0u,
                probe_seen ? (unsigned long long)probe_stat.st_size:0ull);
            if(n>0 && (size_t)n<sizeof message)
                (void)write(probe_receipt_fd,message,(size_t)n);
            (void)close(probe_receipt_fd);
        }
        if(probe_saved!=VH_AUDOUT_QUEUE_EXPORT_OK || !probe_seen) {
            fprintf(stderr,
                "audout probe journal SD export failed: %d, path_present=%d\\n",
                (int)probe_saved,probe_seen);
            export_status=2;
        }
        if (resume_message_enabled)
            (void)appletSetRestartMessageEnabled(false);
    }
    if (log_has_samples) {
        /* ONLY after joining the audio worker, commit a new numbered
         * CSV by closed-temp -> rename. Never truncate a prior report.
         * No filesystem operations take place in an audout callback.
         */
        VhAudioDiagnostics final_sample={0};
        if (audio_started)
            vh_switch_game_audio_diagnostics(&final_sample);
        else
            final_sample.status=-1;
        const uint64_t elapsed_ms=armTicksToNs(
            armGetSystemTick()-session_start_tick)/UINT64_C(1000000);
        if (vh_audio_diag_journal_finish(
                &hardware_audio_log,elapsed_ms,&final_sample)!=1) {
            export_status=2;
        } else {
            (void)mkdir("sdmc:/switch",0777);
            (void)mkdir("sdmc:/switch/vandal-hearts-remake",0777);
            char saved_path[VH_AUDIO_DIAG_EXPORT_PATH_CAP];
            const VhAudioDiagExportResult result=vh_audio_diag_export(
                &hardware_audio_log,"sdmc:/switch/vandal-hearts-remake",
                NULL,saved_path,sizeof saved_path);
            if (result!=VH_AUDIO_EXPORT_OK) {
                fprintf(stderr,"audio diagnostics export failed: %d\n",
                        (int)result);
                export_status=2;
            }
        }
    }
    if(audio_started && optical_receipt_requested) {
        u32 stride_bytes=0;
        u32 *pixels=(u32 *)framebufferBegin(&fb,&stride_bytes);
        if(pixels) {
            VhCanvas canvas={(uint32_t *)pixels,
                             stride_bytes/sizeof(u32),FB_WIDTH,FB_HEIGHT};
            /* Marker is pure magenta to make host screenshot detection
             * independent of the placement of NeXium's native panels.
             * This is a trace byte transport, not audible evidence. */
            const int rendered=vh_switch_game_audio_trace_render(
                &canvas,RGBA8_MAXALPHA(0,0,0),
                RGBA8_MAXALPHA(255,255,255),
                RGBA8_MAXALPHA(255,0,255));
            framebufferEnd(&fb);
            if(rendered>=0) {
                /* Keep the immutable receipt visible for the emulator
                 * screenshot. Only diagnostic Plus+X incurs the delay. */
                svcSleepThread(UINT64_C(5000000000));
            }
        }
    }
    framebufferClose(&fb);
    return export_status;
}
