#include "vh_switch_game_audio.h"

#include <switch.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "vh_audio_resample.h"
#include "vh_game_music_banks.h"
#include "vh_music_scene.h"

/* All large SPU/FIR work buffers are static. The worker preloads
 * two local SD banks (field/selected) before audout starts, falling
 * back to synthetic cues ONLY when both complete sets are absent.
 * No game files, disk reads or VAG decoding occur in the PCM loop.
 */
#define VH_GAME_MUSIC_SD_ROOT "sdmc:/switch/vandal-hearts-remake/audio"
static Thread audio_thread;
static int thread_started;
static VhGameMusicMailbox mailbox;
static atomic_int audio_status;
static atomic_uint bank_warning_notes;
static VhNativeSpu spu;
static VhMusicScene director;
static VhAudioResample rate_converter;
static int16_t synth_samples[128];
static int16_t pcm_44100[VH_AUDIO_BLOCK_FRAMES * 2u];
static int16_t pcm_48000_page[0x1000u / sizeof(int16_t)]
    __attribute__((aligned(0x1000)));

#define PS1_HDR 'p','Q','E','S',0,0,0,0,0x01,0xe0,0x07,0xa1,0x20,0,0
static const uint8_t field_seq[] = {
    PS1_HDR,
    0,0xc0,7,0,0x90,60,110,
    0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f
};
static const uint8_t selected_seq[] = {
    PS1_HDR,
    0,0xc0,7,0,0x90,67,110,
    0x81,0x70,0x80,67,0,
    0x81,0x70,0xff,0x2f
};

static int synthetic_tone(void *unused, unsigned program, unsigned note,
                          unsigned velocity, unsigned volume, unsigned pan,
                          VhSeqTone *tone) {
    (void)unused;
    if (!tone || program != 7 || (note != 60 && note != 67) ||
        velocity > 127u || volume > 127u || pan > 127u) return -1;
    memset(tone, 0, sizeof(*tone));
    tone->pcm = synth_samples;
    tone->frames = 128;
    tone->loop_start = 0;
    tone->loop_end = 128;
    tone->pitch_step = note == 60 ? 4096u : 6144u;
    tone->adsr1 = 15;
    tone->adsr2 = 0;
    tone->reverb_send = 1;
    tone->gain_left = 0.30f * (float)velocity / 127.f;
    tone->gain_right = 0.25f * (float)volume / 127.f;
    return 0;
}

static const VhMusicCue field_cue = {
    VH_GAME_MUSIC_FIELD, field_seq, sizeof(field_seq),
    0, synthetic_tone, NULL
};
static const VhMusicCue selected_cue = {
    VH_GAME_MUSIC_HERO_SELECTED, selected_seq, sizeof(selected_seq),
    0, synthetic_tone, NULL
};

/* On some applet focus transitions the output session may already
 * have been stopped or restarted by the system. Treat an already
 * correct service state as success; other libnx failures are fatal.
 */
static int stop_audout_checked(void) {
    if (R_SUCCEEDED(audoutStopAudioOut())) return 0;
    AudioOutState state;
    return R_SUCCEEDED(audoutGetAudioOutState(&state)) &&
           state == AudioOutState_Stopped ? 0 : -1;
}

static int start_audout_checked(void) {
    if (R_SUCCEEDED(audoutStartAudioOut())) return 0;
    AudioOutState state;
    return R_SUCCEEDED(audoutGetAudioOutState(&state)) &&
           state == AudioOutState_Started ? 0 : -1;
}

static void audio_worker(void *unused) {
    (void)unused;
    int state = -1;
    int opened = 0, playing = 0;
    VhGameMusicBanks *loaded_banks = NULL;
    const int pack_status = vh_game_music_banks_load(
        &loaded_banks, VH_GAME_MUSIC_SD_ROOT);
    if (pack_status == VH_AUDIO_ASSET_OK) {
        const unsigned warnings =
            loaded_banks->field_fallback_notes +
            loaded_banks->selected_fallback_notes +
            loaded_banks->field_audit.missing_notes +
            loaded_banks->selected_audit.missing_notes;
        atomic_store_explicit(&bank_warning_notes, warnings,
                              memory_order_release);
    }
    if (pack_status == VH_AUDIO_ASSET_ERROR) {
        /* A corrupt/incomplete user pack MUST NOT silently play
         * synthetic music. Keep the tactical grid running silently.
         */
        state = -10;
        goto cleanup;
    }
    for (unsigned i=0;i<128u;i++)
        synth_samples[i] = (int16_t)((int)(i * 127u % 18000u) - 9000);
    vh_native_spu_reset(&spu);
    vh_music_scene_init(&director, &spu);
    vh_audio_resample_reset(&rate_converter);
    if (vh_native_spu_set_interpolation(&spu, VH_SPU_GAUSSIAN) ||
        vh_native_spu_set_reverb(&spu, 1, 0.5f))
        goto cleanup;

    if (R_FAILED(audoutInitialize())) { state = -2; goto cleanup; }
    opened = 1;
    if (audoutGetSampleRate() != VH_NATIVE_AUDOUT_RATE ||
        audoutGetChannelCount() != 2u ||
        audoutGetPcmFormat() != PcmFormat_Int16) {
        state = -3;
        goto cleanup;
    }
    /* Initialize the output session, but start playback only when the
     * applet is actually focused. Keeping the service stopped during
     * HOME/sleep avoids stale queued data on resume.
     */
    AudioOutBuffer desc = {0};
    desc.buffer = pcm_48000_page;
    desc.buffer_size = sizeof(pcm_48000_page);

    unsigned accepted = VH_GAME_MUSIC_SILENT;
    unsigned handled_resume =
        vh_game_music_mailbox_resume_serial(&mailbox);
    atomic_store_explicit(&audio_status, 0, memory_order_release);
    while (vh_game_music_mailbox_running(&mailbox)) {
        const unsigned newest_resume =
            vh_game_music_mailbox_resume_serial(&mailbox);
        if (newest_resume != handled_resume) {
            handled_resume = newest_resume;
            /* HOME/sleep can suspend this thread before it sees focus
             * loss. Reopen audout explicitly on resume while keeping
             * SEQ, SPU, reverb and resampler playback positions.
             */
            if (playing) {
                if (stop_audout_checked()) {
                    state = -9;
                    break;
                }
                playing = 0;
            }
        }
        if (!vh_game_music_mailbox_focused(&mailbox)) {
            if (playing) {
                if (stop_audout_checked()) {
                    state = -9;
                    break;
                }
                playing = 0;
            }
            atomic_store_explicit(&audio_status, 2, memory_order_release);
            /* No SEQ block, SPU sample or resampler clock may advance
             * while paused. The main frame loop is never blocked here.
             */
            svcSleepThread(16000000LL);
            continue;
        }
        if (!playing) {
            if (start_audout_checked()) {
                state = -4;
                break;
            }
            playing = 1;
            atomic_store_explicit(&audio_status, 1, memory_order_release);
        }
        /* The game thread only publishes the newest desired state.
         * The audio thread alone owns scene fades and SPU state;
         * requests during a fade are retried on later audio blocks.
         */
        const unsigned desired = vh_game_music_mailbox_read(&mailbox);
        if (desired != accepted) {
            VhMusicCue bank_cue = {0};
            const VhMusicCue *cue = NULL;
            if (desired == VH_GAME_MUSIC_FIELD ||
                desired == VH_GAME_MUSIC_HERO_SELECTED) {
                if (pack_status == VH_AUDIO_ASSET_OK) {
                    if (vh_game_music_banks_cue(
                            loaded_banks, desired, &bank_cue)) {
                        state = -5;
                        break;
                    }
                    cue = &bank_cue;
                } else {
                    cue = desired == VH_GAME_MUSIC_FIELD
                        ? &field_cue : &selected_cue;
                }
            }
            const int change = vh_music_scene_request(
                &director, cue, accepted ? 8u : 0u);
            if (change == 0) accepted = desired;
            else if (change != -2) { state = -5; break; }
        }
        if (vh_music_scene_render(&director, pcm_44100) != 0) {
            state = -6;
            break;
        }
        const size_t count = vh_audio_resample_process(
            &rate_converter, pcm_44100, VH_AUDIO_BLOCK_FRAMES,
            pcm_48000_page, VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if (!count || count * 2u * sizeof(int16_t) > desc.buffer_size) {
            state = -7;
            break;
        }
        desc.data_size = count * 2u * sizeof(int16_t);
        AudioOutBuffer *released = NULL;
        if (R_FAILED(audoutPlayBuffer(&desc, &released))) {
            state = -8;
            break;
        }
    }
    if (state == -1) state = 0; /* clean stop requested by main thread */
cleanup:
    if (playing) (void)stop_audout_checked();
    if (opened) audoutExit();
    /* All queued buffers are done; discard every borrowed bank/PCM
     * voice pointer before finally freeing the two local asset sets.
     */
    /* audout is stopped/exited before detaching borrowed bank memory.
     * This also cancels a fade or a queued second-bank cue; no SEQ,
     * SPU voice or wet reverb state may retain a freed PCM pointer. */
    if (director.spu == &spu)
        (void)vh_music_scene_detach(&director);
    else
        vh_native_spu_reset(&spu);
    vh_music_scene_init(&director, &spu);
    vh_game_music_banks_close(&loaded_banks);
    atomic_store_explicit(&audio_status, state, memory_order_release);
}

int vh_switch_game_audio_start(unsigned initial_scene) {
    if (thread_started || initial_scene > VH_GAME_MUSIC_HERO_SELECTED)
        return -1;
    vh_game_music_mailbox_init(&mailbox, initial_scene);
    atomic_store_explicit(&audio_status, 0, memory_order_release);
    atomic_store_explicit(&bank_warning_notes, 0u,
                          memory_order_release);
    Result rc = threadCreate(&audio_thread, audio_worker, NULL,
                             NULL, 0x10000u, 0x2Cu, -2);
    if (R_FAILED(rc)) return -1;
    rc = threadStart(&audio_thread);
    if (R_FAILED(rc)) {
        threadClose(&audio_thread);
        return -1;
    }
    thread_started = 1;
    return 0;
}

void vh_switch_game_audio_post(unsigned desired_scene) {
    if (thread_started)
        vh_game_music_mailbox_post(&mailbox, desired_scene);
}

void vh_switch_game_audio_set_focus(int in_focus) {
    if (!thread_started) return;
    /* A focus-loss event can arrive just before libnx suspends every
     * user thread. On the subsequent first in-focus frame, request
     * explicit audout recovery even if OnResume was never delivered.
     */
    if (in_focus && !vh_game_music_mailbox_focused(&mailbox))
        vh_game_music_mailbox_on_resume(&mailbox, 1);
    else
        vh_game_music_mailbox_set_focus(&mailbox, in_focus);
}

void vh_switch_game_audio_on_resume(int in_focus) {
    if (thread_started)
        vh_game_music_mailbox_on_resume(&mailbox, in_focus);
}

int vh_switch_game_audio_status(void) {
    return atomic_load_explicit(&audio_status, memory_order_acquire);
}

unsigned vh_switch_game_audio_bank_warnings(void) {
    return atomic_load_explicit(&bank_warning_notes,
                                memory_order_acquire);
}

void vh_switch_game_audio_stop(void) {
    if (!thread_started) return;
    vh_game_music_mailbox_stop(&mailbox);
    /* The only blocking join happens at exit, never in the frame loop. */
    threadWaitForExit(&audio_thread);
    threadClose(&audio_thread);
    thread_started = 0;
}
