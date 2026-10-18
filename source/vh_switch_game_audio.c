#include "vh_switch_game_audio.h"
/* Only explicit research builds may select a different pre-submit
 * SERVICE query phase. Normal released NRO and all legacy CSVs stay phase0. */
#ifndef VH_AUDOUT_PROBE_PHASE
#define VH_AUDOUT_PROBE_PHASE 0
#endif
#if VH_AUDOUT_PROBE_PHASE < 0 || VH_AUDOUT_PROBE_PHASE >= 16
#error "VH_AUDOUT_PROBE_PHASE must be in [0,15]"
#endif
#include "vh_audio_scene_trace.h"
#include "vh_audio_scene_optical.h"
#include "vh_audio_exit_timeline.h"
#include "vh_audio_exit_output_witness.h"
#include "vh_audio_exit_worker_stop_witness.h"
#include "vh_audio_worker_stop_gate.h"
#include "vh_audio_last_playbuffer_call.h"
#include "vh_audio_playbuffer_history.h"

#include <stdio.h>

#include <switch.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "vh_audio_resample.h"
#include "vh_audio_output_recovery.h"
#include "vh_audio_buffer_lease.h"
#include "vh_audout_queue_telemetry.h"
#include "vh_audout_queue_export.h"
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
/* Two producer threads reserve immutable slots, then release-publish.
 * No heap, locks or file I/O in this path. */
static VhAudioSceneTrace scene_trace;
static VhAudioExitTimeline exit_timeline; /* only once per audio start */
static VhAudioExitOutputWitness exit_output_witness; /* audio owner only */
static VhAudioExitWorkerStopWitness worker_stop_witness;
static VhAudioLastPlayBufferCall last_playbuffer_call; /* same owner, existing clocks */
static VhPlayBufferHistory last_playbuffer_history; /* last 16 real calls */
/* Audout worker is the sole writer. Main reads after thread join. */
static VhAudoutQueueTelemetry audout_telemetry;
static atomic_ullong scene_trace_latest_ticket; /* serial << 32 | scene */
static unsigned main_scene_serial; /* game thread only */
static uint64_t scene_trace_now_ns(void) {
    return armTicksToNs(armGetSystemTick());
}
static void scene_trace_emit(VhAudioSceneTraceKind kind,
                             unsigned serial, unsigned scene) {
    (void)vh_audio_scene_trace_record(&scene_trace,kind,serial,scene,
                                      scene_trace_now_ns());
}
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
    /* Query service-reported queue length periodically BEFORE submit.
     * This call can fail on firmware without the 4.0.0+ command; a
     * telemetry failure must never alter playback/recovery semantics.
     * Neither the pre-submit count nor lease ownership proves the
     * real-time playback queue depth while PlayBuffer is blocking. */
    int queue_status=-1;
    u32 queue_count=0;
    if(vh_audout_queue_probe_due(&audout_telemetry)) {
        queue_status=R_SUCCEEDED(
            audoutGetAudioOutBufferCount(&queue_count)) ? 1 : 0;
    }
    AudioOutBuffer *released = NULL;
    const uint64_t begin_ns=scene_trace_now_ns();
    const Result played=audoutPlayBuffer(s->buffer,&released);
    const int returned=R_SUCCEEDED(played) &&
        vh_audio_buffer_lease_release(&s->lease,released)==0;
    /* Record exactly ONE already-existing end timestamp. The new
     * witness adds no clock queries and never influences audio result. */
    const uint64_t end_ns=scene_trace_now_ns();
    vh_audout_queue_record(&audout_telemetry,begin_ns,
        end_ns,returned,queue_status,queue_count);
    (void)vh_audio_last_playbuffer_record(
        &last_playbuffer_call,begin_ns,end_ns,returned);
    (void)vh_playbuffer_history_record(
        &last_playbuffer_history,begin_ns,end_ns,returned);
    return returned ? 0 : -1;
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
    unsigned pending_trace_serial = 0, pending_trace_scene = 0;
    int pending_trace_page = 0;
    unsigned handled_resume =
        vh_game_music_mailbox_resume_serial(&mailbox);
    int pending_resume_reopen = 0;
    atomic_store_explicit(&audio_status, 0, memory_order_release);
    for (;;) {
        /* One existing running-flag read; zero clock queries while
         * PCM production continues. Only after observing running==0
         * stamp the one-shot software marker and leave the loop. */
        if (!vh_audio_worker_stop_gate_continue(
                &mailbox,&worker_stop_witness,scene_trace_now_ns))
            break;
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
        /* Stable ticket reads prevent attaching a newer button serial
         * to an older mailbox value. Ambiguity falls back to serial 0. */
        const uint64_t ticket_before=atomic_load_explicit(
            &scene_trace_latest_ticket,memory_order_acquire);
        const unsigned desired=vh_game_music_mailbox_read(&mailbox);
        const uint64_t ticket_after=atomic_load_explicit(
            &scene_trace_latest_ticket,memory_order_acquire);
        const unsigned desired_serial=
            ticket_before==ticket_after && (unsigned)ticket_after==desired
            ? (unsigned)(ticket_after>>32) : 0u;
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
            if (change == 0) {
                accepted = desired;
                scene_trace_emit(VH_SCENE_TRACE_ACCEPT,desired_serial,desired);
                pending_trace_serial=desired_serial;
                pending_trace_scene=desired;
                pending_trace_page=1;
            }
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
        /* Single-page audout call can wait for a released descriptor.
         * SUBMIT_CALL is not proof of audible start and RELEASE_RETURN
         * means recovery/lease confirmation, not DAC/speaker playback. */
        if (pending_trace_page)
            scene_trace_emit(VH_SCENE_TRACE_SUBMIT_CALL,
                             pending_trace_serial,pending_trace_scene);
        if (vh_audio_output_submit_recover(&recovery_ops,
                                           &recovery_stats,
                                           pcm_48000_page,count)) {
            if (pending_trace_page)
                scene_trace_emit(VH_SCENE_TRACE_SUBMIT_ERROR,
                                 pending_trace_serial,pending_trace_scene);
            state=-8;
            break;
        }
        if (pending_trace_page) {
            scene_trace_emit(VH_SCENE_TRACE_RELEASE_RETURN,
                             pending_trace_serial,pending_trace_scene);
            pending_trace_page=0;
        }
        /* Submission returned ownership of THIS exact 48-kHz page.
         * Store the terminal sample for optional normal-exit taper;
         * never inspect or overwrite it while the device owns it. */
        /* One timestamp AFTER final ownership return for this original
         * PCM page. Never a claim of audible playback or DAC drain. */
        (void)vh_audio_exit_output_page_returned(
            &exit_output_witness,scene_trace_now_ns(),count);
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
    (void)vh_audio_exit_timeline_mark(&exit_timeline,
        VH_EXIT_WORKER_CLEANUP_ENTERED,scene_trace_now_ns());
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
            last_pcm_left,last_pcm_right)) {
        const uint64_t tail_begin=scene_trace_now_ns();
        const int tail_returned=output_tail_submit_bounded(
            &recovery_backend,VH_AUDIO_STOP_TAIL_FRAMES)==0;
        (void)vh_audio_exit_output_tail(
            &exit_output_witness,tail_begin,scene_trace_now_ns(),tail_returned);
    }
    /* A stopped audout service may retain queued buffers. Close the
     * old session BEFORE overwriting or releasing the shared PCM page.
     */
    (void)output_stop(&recovery_backend);
    output_close(&recovery_backend);
    (void)vh_audio_exit_timeline_mark(&exit_timeline,
        VH_EXIT_AUDOUT_CLOSED,scene_trace_now_ns());
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
    vh_audio_scene_trace_init(&scene_trace);
    vh_audio_exit_timeline_reset(&exit_timeline);
    vh_audio_exit_output_reset(&exit_output_witness);
    vh_audio_exit_worker_stop_reset(&worker_stop_witness);
    vh_audio_last_playbuffer_reset(&last_playbuffer_call);
    vh_playbuffer_history_reset(&last_playbuffer_history);
    vh_audout_queue_reset(&audout_telemetry);
    if(vh_audout_queue_set_probe_phase(&audout_telemetry,
                                      VH_AUDOUT_PROBE_PHASE)) return -1;
    main_scene_serial=0u;
    atomic_store_explicit(&scene_trace_latest_ticket,
                          (uint64_t)initial_scene,memory_order_release);
    vh_game_music_mailbox_init(&mailbox,initial_scene);
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

void vh_switch_game_audio_post_at(unsigned desired_scene,
                                  uint64_t input_observed_ns) {
    if (!thread_started || desired_scene>VH_GAME_MUSIC_HERO_SELECTED) return;
    /* Single writer on main; latest desired scene wins in mailbox. */
    const unsigned serial=++main_scene_serial;
    (void)vh_audio_scene_trace_record(&scene_trace,
                                      VH_SCENE_TRACE_INPUT,serial,
                                      desired_scene,input_observed_ns);
    scene_trace_emit(VH_SCENE_TRACE_POST,serial,desired_scene);
    atomic_store_explicit(&scene_trace_latest_ticket,
                          ((uint64_t)serial<<32)|desired_scene,
                          memory_order_release);
    vh_game_music_mailbox_post(&mailbox,desired_scene);
}
void vh_switch_game_audio_post(unsigned desired_scene) {
    vh_switch_game_audio_post_at(desired_scene,scene_trace_now_ns());
}
VhSceneExportResult vh_switch_game_audio_trace_export(
    char *committed_path, size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_SCENE_EXPORT_INVALID;
    return vh_audio_scene_trace_export(&scene_trace,
        VH_SCENE_TRACE_SD_DIRECTORY,NULL,committed_path,capacity);
}

int vh_switch_game_audio_trace_render(VhCanvas *canvas,
    uint32_t black,uint32_t white,uint32_t marker) {
    if(thread_started) return -1;
    return vh_audio_scene_optical_draw(canvas,&scene_trace,
                                        black,white,marker);
}

VhAudoutQueueExportResult vh_switch_game_audio_queue_export(
    char *committed_path,size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    return vh_audout_queue_export(&audout_telemetry,
        VH_SCENE_TRACE_SD_DIRECTORY,committed_path,capacity);
}

VhAudoutQueueExportResult vh_switch_game_audio_slow_export(
    char *committed_path,size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    return vh_audout_slow_export(&audout_telemetry,
        VH_SCENE_TRACE_SD_DIRECTORY,committed_path,capacity);
}

VhAudoutQueueExportResult vh_switch_game_audio_clock_export(
    char *committed_path,size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    return vh_audout_clock_export(&audout_telemetry,
        VH_SCENE_TRACE_SD_DIRECTORY,committed_path,capacity);
}

VhAudoutQueueExportResult vh_switch_game_audio_latency_export(
    char *committed_path,size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    return vh_audout_latency_export(&audout_telemetry,
        VH_SCENE_TRACE_SD_DIRECTORY,committed_path,capacity);
}

VhAudoutQueueExportResult vh_switch_game_audio_probe_export(
    char *committed_path,size_t capacity) {
    if(committed_path && capacity) committed_path[0]='\0';
    if(thread_started) return VH_AUDOUT_QUEUE_EXPORT_INVALID;
    return vh_audout_probe_export(&audout_telemetry,
        VH_SCENE_TRACE_SD_DIRECTORY,committed_path,capacity);
}

int vh_switch_game_audio_queue_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_audout_queue_write_csv(&audout_telemetry,stream);
}

int vh_switch_game_audio_trace_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    if (fputs("VH_AUDIO_SCENE_TRACE_BEGIN\n",stream)<0) return -1;
    const int rows=vh_audio_scene_trace_write_csv(&scene_trace,stream);
    if (rows<0 || fprintf(stream,
            "VH_AUDIO_SCENE_TRACE_END,rows=%d,dropped=%u\n",
            rows,vh_audio_scene_trace_dropped(&scene_trace))<0) return -1;
    return rows;
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

void vh_switch_game_audio_exit_note_plus(void) {
    if (thread_started)
        (void)vh_audio_exit_timeline_mark(&exit_timeline,
            VH_EXIT_PLUS_OBSERVED,scene_trace_now_ns());
}

int vh_switch_game_audio_exit_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_audio_exit_timeline_write_csv(&exit_timeline,stream);
}

/* Diagnostic counters are immutable once the audio owner joins.
 * This never changes Stage307's existing five-row CSV source. */
int vh_switch_game_audio_exit_output_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_audio_exit_output_write_csv(&exit_output_witness,stream);
}

int vh_switch_game_audio_worker_stop_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_audio_exit_worker_stop_write_csv(&worker_stop_witness,stream);
}

int vh_switch_game_audio_last_playbuffer_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_audio_last_playbuffer_write_csv(&last_playbuffer_call,stream);
}

int vh_switch_game_audio_playbuffer_history_dump(FILE *stream) {
    if (!stream || thread_started) return -1;
    return vh_playbuffer_history_write_csv(&last_playbuffer_history,stream);
}

void vh_switch_game_audio_stop(void) {
    if (!thread_started) return;
    (void)vh_audio_exit_timeline_mark(&exit_timeline,
        VH_EXIT_STOP_REQUESTED,scene_trace_now_ns());
    vh_game_music_mailbox_stop(&mailbox);
    /* The only blocking join happens at exit, never in the frame loop. */
    threadWaitForExit(&audio_thread);
    threadClose(&audio_thread);
    thread_started = 0;
    (void)vh_audio_exit_timeline_mark(&exit_timeline,
        VH_EXIT_WORKER_JOINED,scene_trace_now_ns());
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
