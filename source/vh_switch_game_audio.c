#include "vh_switch_game_audio.h"

#include <switch.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "vh_audio_resample.h"
#include "vh_audio_output_recovery.h"
#include "vh_audio_buffer_lease.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_output_edges.h"
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
static atomic_uint resume_latency_samples;
static atomic_ullong resume_latency_worst_us;
static atomic_ullong resume_latency_last_us;
static atomic_ullong published_pages;
static atomic_ullong published_frames;
static atomic_uint published_resume_events;
static atomic_uint published_submit_failures;
static atomic_uint published_restart_attempts;
static atomic_uint published_recoveries;
static atomic_uint published_resume_failures;
static atomic_uint published_resume_restarts;
static atomic_uint published_resume_recoveries;
static atomic_uint published_lease_mismatches;
static atomic_uint published_abandoned_sessions;
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

/* Owned exclusively by the audout worker. Recreate a lost output
 * session without advancing music clocks or regenerating a PCM block.
 */
typedef struct {
    int *opened, *playing;
    AudioOutBuffer *buffer;
    VhAudioBufferLease lease; /* only freed when this session closes */
} VhSwitchOutput;

static int output_submit(void *opaque, const int16_t *stereo,
                         size_t frames) {
    VhSwitchOutput *s = opaque;
    if (!*s->opened || !*s->playing ||
        stereo != pcm_48000_page ||
        !frames || frames > VH_AUDIO_RESAMPLE_MAX_FRAMES ||
        frames * 2u * sizeof(int16_t) > s->buffer->buffer_size)
        return -1;
    /* libnx audoutPlayBuffer waits for ANY released buffer. Reusing
     * our single 0x1000-aligned PCM page before its exact descriptor
     * is released could overwrite samples still playing on hardware.
     * An ambiguous/error result retains the lease until audoutExit.
     */
    if (vh_audio_buffer_lease_begin(&s->lease,s->buffer)) return -1;
    s->buffer->next = NULL;
    s->buffer->data_offset = 0;
    s->buffer->data_size = frames * 2u * sizeof(int16_t);
    AudioOutBuffer *released = NULL;
    if (R_FAILED(audoutPlayBuffer(s->buffer,&released))) return -1;
    return vh_audio_buffer_lease_release(&s->lease,released);
}

static int output_stop(void *opaque) {
    VhSwitchOutput *s = opaque;
    if (!*s->playing) return 0;
    if (stop_audout_checked()) return -1;
    *s->playing = 0;
    return 0;
}

static void output_close(void *opaque) {
    VhSwitchOutput *s = opaque;
    if (*s->opened) {
        audoutExit();
        *s->opened = 0;
    }
    /* A stopped service can still own queued audio. Never clear the
     * lease after stop alone; audoutExit discards the old session.
     */
    vh_audio_buffer_lease_session_closed(&s->lease);
    s->buffer->next = NULL;
    s->buffer->data_size = 0;
    s->buffer->data_offset = 0;
}

static int output_open(void *opaque) {
    VhSwitchOutput *s = opaque;
    if (*s->opened || s->lease.in_flight ||
        R_FAILED(audoutInitialize())) return -1;
    *s->opened = 1;
    return audoutGetSampleRate()==VH_NATIVE_AUDOUT_RATE &&
           audoutGetChannelCount()==2u &&
           audoutGetPcmFormat()==PcmFormat_Int16 ? 0 : -1;
}

static int output_start(void *opaque) {
    VhSwitchOutput *s = opaque;
    if (!*s->opened || start_audout_checked()) return -1;
    *s->playing = 1;
    return 0;
}

/* Cooperative app exit only, while audout is still focused and
 * playing. Unlike PlayBuffer this wait is time-bounded: an applet
 * focus-loss/sleep transition MUST use the immediate stop path.
 * Failure leaves the lease held until output_close/audoutExit.
 */
static int output_tail_submit_bounded(VhSwitchOutput *s, size_t frames) {
    if (!s || !*s->opened || !*s->playing ||
        !frames || frames>VH_AUDIO_STOP_TAIL_FRAMES ||
        vh_audio_buffer_lease_begin(&s->lease,s->buffer))
        return -1;
    s->buffer->next=NULL;
    s->buffer->data_offset=0;
    s->buffer->data_size=frames*2u*sizeof(int16_t);
    if (R_FAILED(audoutAppendAudioOutBuffer(s->buffer))) return -1;
    AudioOutBuffer *released=NULL;
    u32 released_count=0;
    /* 2-ms buffer and generous <=12-ms wait; never infinite after
     * the main loop has requested that the audio worker stop. */
    if (R_FAILED(audoutWaitPlayFinish(
            &released,&released_count,UINT64_C(12000000))) ||
        !released_count)
        return -1;
    return vh_audio_buffer_lease_release(&s->lease,released);
}

/* Called by the single audio owner; the render thread only takes
 * atomic snapshots. These metrics must NEVER block audout or expose
 * raw PCM/music pointers to the game or renderer threads. */
static void publish_audio_diagnostics(const VhAudioOutputRecovery *r,
                                      const VhAudioBufferLease *lease) {
    atomic_store_explicit(&published_pages,r->pages_submitted,
                          memory_order_release);
    atomic_store_explicit(&published_frames,r->frames_submitted,
                          memory_order_release);
    atomic_store_explicit(&published_submit_failures,r->submit_failures,
                          memory_order_release);
    atomic_store_explicit(&published_restart_attempts,r->restart_attempts,
                          memory_order_release);
    atomic_store_explicit(&published_recoveries,r->recoveries,
                          memory_order_release);
    atomic_store_explicit(&published_resume_failures,r->resume_failures,
                          memory_order_release);
    atomic_store_explicit(&published_resume_restarts,r->resume_restarts,
                          memory_order_release);
    atomic_store_explicit(&published_resume_recoveries,r->resume_recoveries,
                          memory_order_release);
    atomic_store_explicit(&published_lease_mismatches,
                          lease->mismatched_releases,
                          memory_order_release);
    atomic_store_explicit(&published_abandoned_sessions,
                          lease->abandoned_sessions,
                          memory_order_release);
}

static void audio_worker(void *unused) {
    (void)unused;
    int state = -1;
    int opened = 0, playing = 0;
    /* Available also on startup failure paths that jump to cleanup. */
    AudioOutBuffer desc = {0};
    desc.buffer = pcm_48000_page;
    desc.buffer_size = sizeof(pcm_48000_page);
    VhSwitchOutput recovery_backend = {
        .opened=&opened, .playing=&playing, .buffer=&desc
    };
    const VhAudioOutputOps recovery_ops = {
        &recovery_backend, output_submit, output_stop, output_close,
        output_open, output_start
    };
    VhAudioOutputRecovery recovery_stats = {0};
    VhAudioOutputRamp output_ramp = {VH_AUDIO_OUTPUT_RAMP_FRAMES};
    VhAudioResumeLatency resume_stats = {0};
    uint64_t resume_begin_tick = 0;
    int16_t last_pcm_left = 0, last_pcm_right = 0;
    int have_last_pcm = 0;
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
    /* Descriptor and session lease were initialized before startup
     * so all early error exits can close output safely as well. */

    unsigned accepted = VH_GAME_MUSIC_SILENT;
    unsigned handled_resume =
        vh_game_music_mailbox_resume_serial(&mailbox);
    int pending_resume_reopen = 0;
    atomic_store_explicit(&audio_status, 0, memory_order_release);
    while (vh_game_music_mailbox_running(&mailbox)) {
        const unsigned newest_resume =
            vh_game_music_mailbox_resume_serial(&mailbox);
        if (newest_resume != handled_resume) {
            handled_resume = newest_resume;
            /* Mark the audout session stale even if the service still
             * reports a valid 'started' state after HOME/sleep. Hold
             * this flag until applet focus returns; no music clocks
             * may advance during the suspended interval. */
            pending_resume_reopen = 1;
            atomic_fetch_add_explicit(&published_resume_events,1u,
                                      memory_order_relaxed);
            if (output_stop(&recovery_backend)) {
                state = -9;
                break;
            }
        }
        if (!vh_game_music_mailbox_focused(&mailbox)) {
            if (output_stop(&recovery_backend)) {
                state = -9;
                break;
            }
            atomic_store_explicit(&audio_status, 2, memory_order_release);
            /* No SEQ block, SPU sample or resampler clock may advance
             * while paused. The main frame loop is never blocked here.
             */
            svcSleepThread(16000000LL);
            continue;
        }
        if (!playing) {
            const uint64_t start_tick=armGetSystemTick();
            if (vh_audio_output_resume_recover(
                    &recovery_ops, &recovery_stats,
                    pending_resume_reopen)) {
                state = -4;
                break;
            }
            pending_resume_reopen = 0;
            /* Only the next freshly rendered PCM frames fade in.
             * A PlayBuffer retry resubmits the already modified page,
             * not a second pass through this envelope. */
            vh_audio_output_ramp_arm(&output_ramp);
            resume_begin_tick=start_tick;
            publish_audio_diagnostics(&recovery_stats,
                                      &recovery_backend.lease);
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
        if (!count || count * 2u * sizeof(int16_t) > desc.buffer_size ||
            vh_audio_output_ramp_apply(&output_ramp,
                                       pcm_48000_page,count)) {
            state = -7;
            break;
        }
        /* If audout rejects the page, reinitialize the device and
         * retry exactly these samples. Never re-run scene/render or
         * resampler for the same page (that would skip musical time).
         * Bounded retries fail closed through the normal teardown. */
        if (vh_audio_output_submit_recover(&recovery_ops,
                                           &recovery_stats,
                                           pcm_48000_page, count)) {
            state = -8;
            break;
        }
        /* Submission returned ownership of THIS exact 48-kHz page.
         * Store the terminal sample for optional normal-exit taper;
         * never inspect or overwrite it while the device owns it. */
        publish_audio_diagnostics(&recovery_stats,
                                  &recovery_backend.lease);
        last_pcm_left=pcm_48000_page[2u*count-2u];
        last_pcm_right=pcm_48000_page[2u*count-1u];
        have_last_pcm=1;
        if (resume_begin_tick) {
            const uint64_t elapsed_ns=armTicksToNs(
                armGetSystemTick()-resume_begin_tick);
            vh_audio_resume_latency_record(&resume_stats,elapsed_ns);
            const unsigned samples=resume_stats.count>UINT32_MAX
                ? UINT32_MAX : (unsigned)resume_stats.count;
            atomic_store_explicit(&resume_latency_samples,samples,
                                  memory_order_release);
            atomic_store_explicit(&resume_latency_worst_us,
                resume_stats.max_ns/UINT64_C(1000),
                memory_order_release);
            atomic_store_explicit(&resume_latency_last_us,
                resume_stats.last_ns/UINT64_C(1000),
                memory_order_release);
            resume_begin_tick=0;
        }
    }
    if (state == -1) state = 0; /* clean stop requested by main thread */
cleanup:
    /* A cooperative exit may send a SHORT last-sample-to-zero tail.
     * Never attempt output after HOME/focus loss: audout can already
     * be suspended, and a non-bounded submit could deadlock shutdown.
     * This tail is not produced by SEQ/SPU/resampler and cannot move
     * musical time; any output error simply falls through to close.
     */
    if (state==0 && playing &&
        vh_game_music_mailbox_focused(&mailbox) && have_last_pcm &&
        (last_pcm_left || last_pcm_right) &&
        !recovery_backend.lease.in_flight &&
        !vh_audio_stop_tail_build(
            pcm_48000_page,
            sizeof(pcm_48000_page)/(2u*sizeof(int16_t)),
            last_pcm_left,last_pcm_right))
        (void)output_tail_submit_bounded(&recovery_backend,
                                         VH_AUDIO_STOP_TAIL_FRAMES);
    /* A stopped audout service may retain queued buffers. Close the
     * old session BEFORE overwriting or releasing the shared PCM page.
     */
    (void)output_stop(&recovery_backend);
    output_close(&recovery_backend);
    memset(pcm_48000_page,0,sizeof(pcm_48000_page));
    /* All queued buffers have been invalidated with the session;
     * discard every borrowed bank/PCM voice pointer before freeing.
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
    publish_audio_diagnostics(&recovery_stats,
                              &recovery_backend.lease);
    atomic_store_explicit(&audio_status, state, memory_order_release);
}

int vh_switch_game_audio_start(unsigned initial_scene) {
    if (thread_started || initial_scene > VH_GAME_MUSIC_HERO_SELECTED)
        return -1;
    vh_game_music_mailbox_init(&mailbox, initial_scene);
    atomic_store_explicit(&audio_status, 0, memory_order_release);
    atomic_store_explicit(&bank_warning_notes, 0u,
                          memory_order_release);
    atomic_store_explicit(&resume_latency_samples, 0u,
                          memory_order_release);
    atomic_store_explicit(&resume_latency_worst_us, 0u,
                          memory_order_release);
    atomic_store_explicit(&resume_latency_last_us, 0u,
                          memory_order_release);
    atomic_store_explicit(&published_pages, 0u, memory_order_release);
    atomic_store_explicit(&published_frames, 0u, memory_order_release);
    atomic_store_explicit(&published_resume_events,0u,memory_order_release);
    atomic_store_explicit(&published_submit_failures,0u,memory_order_release);
    atomic_store_explicit(&published_restart_attempts,0u,memory_order_release);
    atomic_store_explicit(&published_recoveries,0u,memory_order_release);
    atomic_store_explicit(&published_resume_failures,0u,memory_order_release);
    atomic_store_explicit(&published_resume_restarts,0u,memory_order_release);
    atomic_store_explicit(&published_resume_recoveries,0u,memory_order_release);
    atomic_store_explicit(&published_lease_mismatches,0u,memory_order_release);
    atomic_store_explicit(&published_abandoned_sessions,0u,memory_order_release);
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

unsigned vh_switch_game_audio_resume_latency_samples(void) {
    return atomic_load_explicit(&resume_latency_samples,
                                memory_order_acquire);
}

uint64_t vh_switch_game_audio_resume_worst_confirmed_us(void) {
    return (uint64_t)atomic_load_explicit(&resume_latency_worst_us,
                                         memory_order_acquire);
}

void vh_switch_game_audio_diagnostics(VhAudioDiagnostics *out) {
    if (!out) return;
    out->status=vh_switch_game_audio_status();
    out->bank_warnings=vh_switch_game_audio_bank_warnings();
    out->resume_events=atomic_load_explicit(&published_resume_events,
                                             memory_order_acquire);
    out->confirmed_resumes=vh_switch_game_audio_resume_latency_samples();
    out->last_confirmed_us=(uint64_t)atomic_load_explicit(
        &resume_latency_last_us,memory_order_acquire);
    out->worst_confirmed_us=
        vh_switch_game_audio_resume_worst_confirmed_us();
    out->pages_submitted=(uint64_t)atomic_load_explicit(
        &published_pages,memory_order_acquire);
    out->frames_submitted=(uint64_t)atomic_load_explicit(
        &published_frames,memory_order_acquire);
    out->submit_failures=atomic_load_explicit(
        &published_submit_failures,memory_order_acquire);
    out->restart_attempts=atomic_load_explicit(
        &published_restart_attempts,memory_order_acquire);
    out->recoveries=atomic_load_explicit(
        &published_recoveries,memory_order_acquire);
    out->resume_failures=atomic_load_explicit(
        &published_resume_failures,memory_order_acquire);
    out->resume_restarts=atomic_load_explicit(
        &published_resume_restarts,memory_order_acquire);
    out->resume_recoveries=atomic_load_explicit(
        &published_resume_recoveries,memory_order_acquire);
    out->lease_mismatches=atomic_load_explicit(
        &published_lease_mismatches,memory_order_acquire);
    out->abandoned_sessions=atomic_load_explicit(
        &published_abandoned_sessions,memory_order_acquire);
}
