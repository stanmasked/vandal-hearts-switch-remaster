/* Combined native software framebuffer plus PS1 SEQ/VAB/SPU -> audout.
 * Plays locally supplied, user-owned music.seq/.vh/.vb from SD; in their
 * absence it renders generated fixture notes. Original copyrighted data
 * is NOT embedded. Audibility and real game logic remain unverified.
 */
#include <switch.h>
#include <stdbool.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>

#include "game_renderer.h"
#include "game_state.h"
#include "platform_input.h"
#include "vh_audio_assets.h"
#include "vh_audio_resample.h"
#include "vh_audio_output_recovery.h"
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#if (defined(VH_AUDIO_GUEST_ZL_AUTOTEST) && defined(VH_AUDIO_GUEST_ZR_AUTOTEST)) || \
    (defined(VH_AUDIO_GUEST_ZL_AUTOTEST) && (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST))) || \
    (defined(VH_AUDIO_GUEST_ZR_AUTOTEST) && (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST))) || \
    (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) && defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)) || \
    (defined(VH_AUDIO_HARDWARE_FOCUS_TRACE) && (defined(VH_AUDIO_GUEST_ZL_AUTOTEST) || defined(VH_AUDIO_GUEST_ZR_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)))
#error Only one guest transport experiment may be enabled
#endif
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
#define VH_GUEST_RESUME_EXPECT_RESTARTS 2u
#define VH_GUEST_RESUME_EXPECT_FAILURES 1u
#else
#define VH_GUEST_RESUME_EXPECT_RESTARTS 1u
#define VH_GUEST_RESUME_EXPECT_FAILURES 0u
#endif

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
static atomic_uint pcm_blocks_generated;
static atomic_uint audout_buffers_completed;
static atomic_uint synthetic_scene_switches;
static atomic_uint audout_wait_peak_us;
static atomic_uint audout_switch_page_peak_us;
static atomic_uint audout_switch_pages_recorded;
static atomic_uint audout_waits_longer_than_page;
static atomic_uint audout_failed_returns;
#ifdef VH_AUDIO_HARDWARE_FOCUS_TRACE
/* Console-only evidence: observe REAL libnx applet notifications.
 * This does not fabricate HOME, modify PCM or call audout from hooks. */
static AppletHookCookie hardware_focus_cookie;
static atomic_int hardware_focus_notify_mode;
static atomic_uint hardware_focus_backgrounds;
static atomic_uint hardware_focus_returns;
static atomic_uint hardware_focus_resumes;
static atomic_uint hardware_focus_pages_at_return;
static void hardware_focus_event(AppletHookType kind, void *param) {
    (void)param;
    if (kind==AppletHookType_OnFocusState) {
        const AppletFocusState focus=appletGetFocusState();
        if(focus==AppletFocusState_Background)
            atomic_fetch_add(&hardware_focus_backgrounds,1u);
        else if(focus==AppletFocusState_InFocus &&
                atomic_load(&hardware_focus_backgrounds)>0u) {
            atomic_store(&hardware_focus_pages_at_return,
                         atomic_load(&audout_buffers_completed));
            atomic_fetch_add(&hardware_focus_returns,1u);
        }
    } else if(kind==AppletHookType_OnResume) {
        atomic_fetch_add(&hardware_focus_resumes,1u);
    }
}
#endif
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
/* CI-only: 0 pending, 1 armed, 2 verified, -1 contradiction. */
static atomic_int guest_zr_witness;
static VhNativeSeq guest_zr_seq_before;
static VhNativeSpu guest_zr_spu_before;
static VhAudioResample guest_zr_rate_before;
static uint64_t guest_pcm_fingerprint(const int16_t *pcm,size_t frames) {
    uint64_t hash=UINT64_C(1469598103934665603);
    for(size_t i=0;i<frames*2u;i++) {
        hash^=(uint16_t)pcm[i];
        hash*=UINT64_C(1099511628211);
    }
    return hash;
}
#endif
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
/* CI-only: 0 idle, 1 armed, 2 rejected diagnostic on a returned
 * descriptor with ZERO retry, -1 contradictory guest evidence. */
static atomic_int guest_zl_witness;
static VhNativeSeq guest_zl_seq_before;
static VhNativeSpu guest_zl_spu_before;
static VhAudioResample guest_zl_rate_before;
static uint64_t guest_zl_pcm_fingerprint(const int16_t *pcm,size_t frames) {
    uint64_t hash=UINT64_C(1469598103934665603);
    for(size_t i=0;i<frames*2u;i++) {
        hash^=(uint16_t)pcm[i];
        hash*=UINT64_C(1099511628211);
    }
    return hash;
}
#endif
#if defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)
/* CI-only manual-equivalent X/Y exercise; NEVER a real HOME event.
 * State: 0 pending, 1 quick resumed, 2 next PCM returned,
 * 3 reopen resumed, 4 post-reopen PCM returned, -1 contradiction. */
static atomic_int guest_resume_witness;
static VhNativeSeq guest_resume_seq_before;
static VhNativeSpu guest_resume_spu_before;
static VhAudioResample guest_resume_rate_before;
static uint64_t guest_resume_pcm_hash(void) {
    uint64_t hash=UINT64_C(1469598103934665603);
    for(size_t i=0;i<sizeof(audio_page)/sizeof(audio_page[0]);++i) {
        hash^=(uint16_t)audio_page[i];
        hash*=UINT64_C(1099511628211);
    }
    return hash;
}
#endif
static int audio_active;
static int using_user_files;
static int sdmc_mounted_here;
static int asset_source_status;  /* +1 user; 0 fixture; -1 bad set; -2 SD missing */

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
/* Alternate synthetic cue, same generated VAB bank, different note.
 * User-owned SD SEQ/VH/VB are never automatically switched by this probe.
 */
static const uint8_t fixture_seq_b[] = {
    'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7, 0,0xb0,7,127, 0,0xb0,10,64,
    0,0x90,64,110, 0x81,0x70,0x80,64,0,
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


/* All mutations of the audout service are serialized: startup happens
 * before threadStart, recovery runs only on the worker, and teardown
 * happens only after threadWaitForExit. A rejected PCM page remains intact.
 */
typedef struct {
    AudioOutBuffer page;
    VhAudioSubmitTiming timing;
    VhAudioSceneWaits scene_waits;
    VhAudioPageLease lease;
    VhAudioTransportTimingHealth transport_health;
#if defined(VH_AUDIO_GUEST_ZL_AUTOTEST) || defined(VH_AUDIO_GUEST_ZR_AUTOTEST) || \
    (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST))
    /* Count ACTUAL service entries independently of timing records:
     * a deliberate bad clock leaves timing.calls unchanged even though
     * audoutPlayBuffer physically ran and returned the descriptor. */
    uint64_t service_calls;
#endif
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
    VhAudioSubmitFaultInjection submit_injection;
#endif
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
    VhAudioTimingFaultInjection timing_injection;
#endif
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
    /* One wrapper-level open rejection before audoutInitialize. */
    unsigned fail_next_open, failed_open_injections;
#endif
    int initialized;
    int started;
} NativeOutput;
static NativeOutput native_output;
static VhAudioOutputRecovery output_recovery;

static void native_close(void *opaque) {
    NativeOutput *dev=(NativeOutput *)opaque;
    /* Failed audoutStop retains ownership of the 4-KiB PCM page.
     * Never tear down this service while that descriptor is leased. */
    if (!dev->initialized || dev->started ||
        !vh_audio_page_lease_ready(&dev->lease)) return;
    audoutExit();
    dev->initialized=0;
    dev->started=0;
}
static int native_open(void *opaque) {
    NativeOutput *dev=(NativeOutput *)opaque;
    if (dev->initialized || !vh_audio_page_lease_ready(&dev->lease))
        return -1;
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
    if (dev->fail_next_open) {
        dev->fail_next_open=0u;
        ++dev->failed_open_injections;
        return -1; /* synthetic failure; no real audoutInitialize */
    }
#endif
    if (R_FAILED(audoutInitialize())) return -1;
    dev->initialized=1;
    if (audoutGetSampleRate()!=VH_NATIVE_AUDOUT_RATE ||
        audoutGetChannelCount()!=2 ||
        audoutGetPcmFormat()!=PcmFormat_Int16) {
        native_close(dev);
        return -1;
    }
    memset(&dev->page,0,sizeof(dev->page));
    dev->page.buffer=audio_page;
    dev->page.buffer_size=sizeof(audio_page);
    return dev->page.buffer_size==AUDIO_PAGE_BYTES ? 0 : -1;
}
static int native_start(void *opaque) {
    NativeOutput *dev=(NativeOutput *)opaque;
    if (!dev->initialized || dev->started ||
        !vh_audio_page_lease_ready(&dev->lease) ||
        R_FAILED(audoutStartAudioOut())) return -1;
    dev->started=1;
    return 0;
}
static int native_stop(void *opaque) {
    NativeOutput *dev=(NativeOutput *)opaque;
    if (!dev->started)
        return vh_audio_page_lease_ready(&dev->lease) ? 0 : -1;
    /* Only a confirmed audoutStop can release a mismatched/failed
     * descriptor, after which its backing PCM may be reused. */
    const Result rc=audoutStopAudioOut();
    if (vh_audio_page_lease_stopped(&dev->lease,
            R_SUCCEEDED(rc) ? 0 : -1)) return -1;
    dev->started=0;
    return 0;
}
static int native_submit(void *opaque,const int16_t *pcm,size_t frames) {
    NativeOutput *dev=(NativeOutput *)opaque;
    if (!dev->initialized || !dev->started || pcm!=audio_page ||
        !frames || frames>VH_AUDIO_RESAMPLE_MAX_FRAMES ||
        !vh_audio_page_lease_ready(&dev->lease)) return -1;
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
    /* Exercise a REAL guest audout recovery without forging a service
     * call. The one rejected attempt occurs before audoutPlayBuffer;
     * it is distinctly labelled as synthetic in the shared accumulator. */
    if(dev->submit_injection.armed) {
        if(vh_audio_output_record_synthetic_submit_failure(
               &dev->timing,armGetSystemTickFreq(),frames) ||
           vh_audio_submit_fault_consume(&dev->submit_injection)!=1)
            return -1;
        return -1;
    }
#endif
    /* Lease before changing descriptor fields. A foreign return or
     * service error holds the page until a successful stop. */
    if (vh_audio_page_lease_begin(&dev->lease,&dev->page)) return -1;
    dev->page.data_size=frames*2u*sizeof(int16_t);
    AudioOutBuffer *released=NULL;
    /* Record raw blocking time for each libnx submission attempt.
     * A returned foreign descriptor is not permission to recycle
     * the backing 4-KiB PCM page, even if the call itself succeeded.
     */
    const uint64_t start_ticks=armGetSystemTick();
#if defined(VH_AUDIO_GUEST_ZL_AUTOTEST) || defined(VH_AUDIO_GUEST_ZR_AUTOTEST) || \
    (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST))
    /* Instrument the actual guest libnx boundary, NOT our logical
     * submit wrapper. The pre-service ZR rejection never gets here. */
    if (dev->service_calls==UINT64_MAX) return -1;
    ++dev->service_calls;
#endif
    const Result result=audoutPlayBuffer(&dev->page,&released);
    const uint64_t elapsed=armGetSystemTick()-start_ticks;
    const int accepted=R_SUCCEEDED(result) &&
        vh_audio_output_page_returned(&dev->page,released);
    if (accepted && vh_audio_page_lease_return(&dev->lease,released))
        return -1;
    uint64_t diagnostic_frequency=armGetSystemTickFreq();
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
    diagnostic_frequency=vh_audio_timing_fault_frequency(
        &dev->timing_injection,accepted,diagnostic_frequency);
#endif
    const int timing_rc=vh_audio_output_record_submit_timing(
            &dev->timing,elapsed,diagnostic_frequency,frames,accepted);
    /* The exact PCM descriptor was ALREADY consumed by audout. Reject
     * invalid timing evidence but never replay that accepted buffer. */
    return vh_audio_output_transport_outcome(
        accepted,timing_rc,&dev->transport_health);
}
static const VhAudioOutputOps output_ops={
    &native_output,native_submit,native_stop,
    native_close,native_open,native_start
};

static void audio_worker(void *unused) {
    (void)unused;
    unsigned rendered_blocks=0, fixture_b=0;
    while (!atomic_load(&audio_stop)) {
#if defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)
        /* Run X-equivalent stop/start after exactly 16 real returned
         * buffers; later exercise Y-equivalent stop/close/open/start at
         * 32 returns. No controller or HOME event is fabricated. */
        const int quick_trial=!using_user_files && rendered_blocks==16u &&
            atomic_load(&guest_resume_witness)==0;
        const int reopen_trial=!using_user_files && rendered_blocks==32u &&
            atomic_load(&guest_resume_witness)==2;
        if (quick_trial || reopen_trial) {
            const VhAudioOutputRecovery rec_before=output_recovery;
            const VhAudioSubmitTiming time_before=native_output.timing;
            const VhAudioTransportTimingHealth health_before=
                native_output.transport_health;
            const VhAudioSceneWaits scene_before=native_output.scene_waits;
            const uint64_t service_before=native_output.service_calls;
            const uint64_t pcm_before=guest_resume_pcm_hash();
            guest_resume_seq_before=seq;
            memcpy(&guest_resume_spu_before,&synth,sizeof synth);
            guest_resume_rate_before=resampler;
            const int prepared=native_output.initialized &&
                native_output.started &&
                vh_audio_page_lease_ready(&native_output.lease) &&
                output_recovery.pages_submitted==rendered_blocks &&
                service_before==output_recovery.pages_submitted &&
                time_before.calls==service_before &&
                !health_before.timing_fault &&
                !rec_before.submit_failures &&
                !rec_before.restart_attempts;
            int action=-1;
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
            if(prepared && reopen_trial && !native_output.failed_open_injections)
                native_output.fail_next_open=1u;
#endif
            if(prepared) {
                if(quick_trial) {
                    if(!native_stop(&native_output))
                        action=native_start(&native_output);
                } else {
                    action=vh_audio_output_resume_recover(
                        &output_ops,&output_recovery,1);
                }
            }
            const int counters_ok=quick_trial ?
                (!memcmp(&output_recovery,&rec_before,sizeof rec_before)) :
                (output_recovery.pages_submitted==rec_before.pages_submitted &&
                 output_recovery.frames_submitted==rec_before.frames_submitted &&
                 output_recovery.submit_failures==rec_before.submit_failures &&
                 output_recovery.restart_attempts==rec_before.restart_attempts &&
                 output_recovery.recoveries==rec_before.recoveries &&
                 output_recovery.resume_restarts==
                     rec_before.resume_restarts+VH_GUEST_RESUME_EXPECT_RESTARTS &&
                 output_recovery.resume_recoveries==rec_before.resume_recoveries+1u &&
                 output_recovery.resume_failures==
                     rec_before.resume_failures+VH_GUEST_RESUME_EXPECT_FAILURES);
            const int valid=prepared && action==0 && counters_ok &&
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
                (!reopen_trial || (native_output.failed_open_injections==1u &&
                                   native_output.fail_next_open==0u)) &&
#endif
                native_output.initialized && native_output.started &&
                vh_audio_page_lease_ready(&native_output.lease) &&
                native_output.service_calls==service_before &&
                !memcmp(&native_output.timing,&time_before,sizeof time_before) &&
                !memcmp(&native_output.transport_health,&health_before,
                        sizeof health_before) &&
                !memcmp(&native_output.scene_waits,&scene_before,
                        sizeof scene_before) &&
                pcm_before==guest_resume_pcm_hash() &&
                !memcmp(&seq,&guest_resume_seq_before,sizeof seq) &&
                !memcmp(&synth,&guest_resume_spu_before,sizeof synth) &&
                !memcmp(&resampler,&guest_resume_rate_before,sizeof resampler);
            if(!valid) {
                atomic_store(&guest_resume_witness,-1);
                atomic_store(&audio_fault,12);
                break;
            }
            atomic_store(&guest_resume_witness,quick_trial ? 1 : 3);
        }
#endif
        unsigned switched_this_block=0;
        /* For generated fixtures only, exercise the real transactional
         * SEQ scene-switch API on the owning audio thread. The previous
         * audout page has already returned before reaching this point.
         */
        if (!using_user_files && rendered_blocks &&
            rendered_blocks % 64u == 0u) {
            const uint8_t *next=fixture_b ? fixture_seq : fixture_seq_b;
            const size_t next_size=fixture_b
                ? sizeof(fixture_seq) : sizeof(fixture_seq_b);
            if (vh_native_seq_switch_scene(
                    &seq,next,next_size,&synth,
                    vh_native_vab_resolve,&synthetic_bank,0)) {
                atomic_store(&audio_fault,4);
                break;
            }
            fixture_b^=1u;
            switched_this_block=1u;
        }
        if (vh_native_seq_advance_block(&seq) < 0) {
            atomic_store(&audio_fault, 1);
            break;
        }
        vh_native_spu_render(&synth, in_44100, VH_AUDIO_BLOCK_FRAMES);
        const size_t count = vh_audio_resample_process(
            &resampler, in_44100, VH_AUDIO_BLOCK_FRAMES, audio_page,
            VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if (!count || count * 2u * sizeof(int16_t) > sizeof(audio_page)) {
            atomic_store(&audio_fault, 2);
            break;
        }
        /* A processed PCM block is NOT yet a successfully returned audout
         * buffer. Report the two independently to avoid false playback
         * claims when an output service is stalled. */
        atomic_fetch_add(&pcm_blocks_generated, 1u);
        /* Restart a broken service at most twice, replaying this same
         * already-rendered PCM page. No additional SEQ/SPU frames are
         * synthesized while the backend is recovering.
         */
        const VhAudioSubmitTiming before_submit=native_output.timing;
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
        /* Inject only after sixteen truly returned audio pages. Since
         * ZL cannot create a transport failure, there MUST be precisely
         * one new returned logical page and zero stop/restart/retries. */
        const int guest_zl_trial=!using_user_files && rendered_blocks==16u &&
            atomic_load(&guest_zl_witness)==0;
        VhAudioOutputRecovery zl_before_recovery={0};
        VhAudioSubmitTiming zl_before_timing={0};
        VhAudioTransportTimingHealth zl_before_health={0};
        uint64_t zl_before_pcm=0u;
        uint64_t zl_before_service_calls=0u;
        if(guest_zl_trial) {
            zl_before_recovery=output_recovery;
            zl_before_timing=native_output.timing;
            zl_before_health=native_output.transport_health;
            zl_before_service_calls=native_output.service_calls;
            zl_before_pcm=guest_zl_pcm_fingerprint(audio_page,count);
            guest_zl_seq_before=seq;
            memcpy(&guest_zl_spu_before,&synth,sizeof synth);
            guest_zl_rate_before=resampler;
            if(vh_audio_timing_fault_arm(&native_output.timing_injection)) {
                atomic_store(&guest_zl_witness,-1);
                atomic_store(&audio_fault,11);
                break;
            }
            atomic_store(&guest_zl_witness,1);
        }
#endif
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
        /* Automatic, independent guest experiment. Exactly one armed
         * request after 16 REAL returned descriptors in synthetic mode.
         * Normal user builds have no automatic fault injection. */
        const int guest_zr_trial=!using_user_files && rendered_blocks==16u &&
            atomic_load(&guest_zr_witness)==0;
        VhAudioOutputRecovery before_recovery={0};
        uint64_t before_pcm=0u;
        uint64_t before_service_calls=0u;
        if(guest_zr_trial) {
            before_recovery=output_recovery;
            before_service_calls=native_output.service_calls;
            before_pcm=guest_pcm_fingerprint(audio_page,count);
            guest_zr_seq_before=seq;
            memcpy(&guest_zr_spu_before,&synth,sizeof synth);
            guest_zr_rate_before=resampler;
            if(vh_audio_submit_fault_arm(&native_output.submit_injection)) {
                atomic_store(&guest_zr_witness,-1);
                atomic_store(&audio_fault,6);
                break;
            }
            atomic_store(&guest_zr_witness,1);
        }
#endif
        const int submit_result=vh_audio_output_submit_recover(
            &output_ops,&output_recovery,audio_page,count);
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
        if(guest_zl_trial) {
            /* Never allow a successfully returned descriptor with
             * corrupt timing to trigger a duplicate audout submission.
             * The raw timing counter cannot advance for this deliberately
             * rejected clock, so cross-check logical page counters too. */
            const int valid=submit_result==0 &&
                vh_audio_page_lease_ready(&native_output.lease) &&
                zl_before_service_calls<UINT64_MAX &&
                native_output.service_calls==zl_before_service_calls+1u &&
                vh_audio_output_verify_timing_injection(
                    &native_output.timing_injection,
                    &native_output.transport_health,&output_recovery)==2 &&
                output_recovery.pages_submitted==
                    zl_before_recovery.pages_submitted+1u &&
                output_recovery.frames_submitted==
                    zl_before_recovery.frames_submitted+count &&
                output_recovery.submit_failures==
                    zl_before_recovery.submit_failures &&
                output_recovery.restart_attempts==
                    zl_before_recovery.restart_attempts &&
                output_recovery.recoveries==zl_before_recovery.recoveries &&
                native_output.timing.calls==zl_before_timing.calls &&
                native_output.timing.failed_submissions==
                    zl_before_timing.failed_submissions &&
                native_output.transport_health.delivered_without_timing==
                    zl_before_health.delivered_without_timing+1u &&
                zl_before_pcm==guest_zl_pcm_fingerprint(audio_page,count) &&
                !memcmp(&seq,&guest_zl_seq_before,sizeof seq) &&
                !memcmp(&synth,&guest_zl_spu_before,sizeof synth) &&
                !memcmp(&resampler,&guest_zl_rate_before,sizeof resampler);
            atomic_store(&guest_zl_witness,valid ? 2 : -1);
            /* End the CI-only test here rather than recording invalid
             * timing as a normal scene page. Always show normal pipeline
             * as halted and the independent ZL witness as confirmed. */
            atomic_store(&audio_fault,valid ? 10 : 11);
            break;
        }
#endif
        if (native_output.transport_health.timing_fault) {
            /* A returned descriptor with unmeasurable time is still
             * delivered, not a trigger to resend its PCM. Do not
             * accept unverifiable service timing in this guest run. */
            atomic_store(&audio_fault,8);
            break;
        }
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
        if(guest_zr_trial) {
            const int valid=submit_result==0 &&
                vh_audio_page_lease_ready(&native_output.lease) &&
                before_service_calls<UINT64_MAX &&
                native_output.service_calls==before_service_calls+1u &&
                vh_audio_output_verify_submit_injection(
                    &native_output.submit_injection,&native_output.timing,
                    &output_recovery)==2 &&
                output_recovery.recoveries==before_recovery.recoveries+1u &&
                output_recovery.pages_submitted==before_recovery.pages_submitted+1u &&
                output_recovery.restart_attempts>=
                    before_recovery.restart_attempts+1u &&
                native_output.timing.synthetic_failed_submissions==
                    before_submit.synthetic_failed_submissions+1u &&
                before_pcm==guest_pcm_fingerprint(audio_page,count) &&
                !memcmp(&seq,&guest_zr_seq_before,sizeof seq) &&
                !memcmp(&synth,&guest_zr_spu_before,sizeof synth) &&
                !memcmp(&resampler,&guest_zr_rate_before,sizeof resampler);
            atomic_store(&guest_zr_witness,valid ? 2 : -1);
            if(!valid) {
                atomic_store(&audio_fault,7);
                break;
            }
        }
#endif
        /* Count a successful/failed logical PCM page exactly once,
         * regardless of the raw audoutPlayBuffer attempts inside
         * recovery. Only the very first page after a synthetic
         * switch receives the boundary tag.
         */
        const int telemetry_rc=vh_audio_output_record_scene_page(
            &native_output.scene_waits,&before_submit,
            &native_output.timing,armGetSystemTickFreq(),count,
            (int)switched_this_block,submit_result==0);
        if (telemetry_rc) {
            atomic_store(&audio_fault,5);
            break;
        }
        /* Publish snapshots atomically; only the audio producer may
         * write the detailed, non-atomic timing accumulator.
         */
        const uint64_t peak_us=vh_audio_output_ticks_to_us(
            native_output.scene_waits.ordinary.peak_page_ticks,
            armGetSystemTickFreq());
        const uint64_t switch_peak_us=vh_audio_output_ticks_to_us(
            native_output.scene_waits.first_after_switch.peak_page_ticks,
            armGetSystemTickFreq());
        atomic_store(&audout_wait_peak_us,
                     (unsigned)(peak_us>UINT_MAX ? UINT_MAX : peak_us));
        atomic_store(&audout_switch_page_peak_us,
                     (unsigned)(switch_peak_us>UINT_MAX
                         ? UINT_MAX : switch_peak_us));
        const uint64_t transition_pages=
            native_output.scene_waits.first_after_switch.pages;
        atomic_store(&audout_switch_pages_recorded,
                     (unsigned)(transition_pages>UINT_MAX
                         ? UINT_MAX : transition_pages));
        const uint64_t slow=native_output.timing.waits_longer_than_page;
        const uint64_t failed=native_output.timing.failed_submissions;
        atomic_store(&audout_waits_longer_than_page,
                     (unsigned)(slow>UINT_MAX ? UINT_MAX : slow));
        atomic_store(&audout_failed_returns,
                     (unsigned)(failed>UINT_MAX ? UINT_MAX : failed));
        if (submit_result) {
            atomic_store(&audio_fault, 3);
            break;
        }
        atomic_fetch_add(&audout_buffers_completed, 1u);
#if defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)
        /* Mark each action verified only AFTER the next real returned
         * PCM descriptor; a successful stop/start alone is insufficient. */
        if(rendered_blocks==16u &&
           atomic_load(&guest_resume_witness)==1 &&
           output_recovery.pages_submitted==17u)
            atomic_store(&guest_resume_witness,2);
        if(rendered_blocks==32u &&
           atomic_load(&guest_resume_witness)==3 &&
           output_recovery.pages_submitted==33u &&
           output_recovery.resume_restarts==VH_GUEST_RESUME_EXPECT_RESTARTS &&
           output_recovery.resume_recoveries==1u &&
           output_recovery.resume_failures==VH_GUEST_RESUME_EXPECT_FAILURES &&
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
           native_output.failed_open_injections==1u &&
#endif
           native_output.service_calls==33u)
            atomic_store(&guest_resume_witness,4);
#endif
        if (switched_this_block)
            atomic_fetch_add(&synthetic_scene_switches,1u);
        ++rendered_blocks;
    }
}

static int start_native_audio(void) {
    if (native_open(&native_output) || native_start(&native_output)) {
        (void)native_stop(&native_output);
        native_close(&native_output);
        return 0;
    }
    memset(&output_recovery,0,sizeof(output_recovery));
    memset(&native_output.timing,0,sizeof(native_output.timing));
    memset(&native_output.scene_waits,0,sizeof(native_output.scene_waits));
    memset(&native_output.transport_health,0,sizeof(native_output.transport_health));
#if defined(VH_AUDIO_GUEST_ZL_AUTOTEST) || defined(VH_AUDIO_GUEST_ZR_AUTOTEST) || \
    (defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST))
    native_output.service_calls=0u;
#endif
    Result result;
    atomic_store(&audio_stop, false);
    atomic_store(&audio_fault, 0);
    atomic_store(&pcm_blocks_generated, 0u);
    atomic_store(&audout_buffers_completed, 0u);
    atomic_store(&synthetic_scene_switches, 0u);
    atomic_store(&audout_wait_peak_us,0u);
    atomic_store(&audout_switch_page_peak_us,0u);
    atomic_store(&audout_switch_pages_recorded,0u);
    atomic_store(&audout_waits_longer_than_page,0u);
    atomic_store(&audout_failed_returns,0u);
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
    atomic_store(&guest_zr_witness,0);
    native_output.submit_injection=(VhAudioSubmitFaultInjection){0};
#endif
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
    atomic_store(&guest_zl_witness,0);
    native_output.timing_injection=(VhAudioTimingFaultInjection){0};
#endif
#if defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)
    atomic_store(&guest_resume_witness,0);
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
    native_output.fail_next_open=0u;
    native_output.failed_open_injections=0u;
#endif
#endif
    result = threadCreate(&sound_thread, audio_worker, NULL, NULL,
                          16 * 1024, 0x2c, -2);
    if (R_FAILED(result)) {
        (void)native_stop(&native_output);
        native_close(&native_output);
        return 0;
    }
    result = threadStart(&sound_thread);
    if (R_FAILED(result)) {
        threadClose(&sound_thread);
        (void)native_stop(&native_output);
        native_close(&native_output);
        return 0;
    }
    return 1;
}

static void stop_native_audio(void) {
    if (!audio_active) return;
    atomic_store(&audio_stop, true);
    (void)threadWaitForExit(&sound_thread);
    threadClose(&sound_thread);
    /* If the device did not stop, keep the descriptor and 4 KiB PCM
     * storage alive until process shutdown. close() refuses to run. */
    if(native_stop(&native_output)) atomic_store(&audio_fault,9);
    native_close(&native_output);
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
    const uint32_t source_missing = RGBA8_MAXALPHA(255, 219, 102);

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
    /* Independent source marker: green = user data; gray = fixture;
     * red = invalid/partial SEQ/VH/VB; amber = SD device unavailable.
     * A green audio SERVICE status alone never proves this is user music. */
    const uint32_t source_color =
        asset_source_status == 1 ? sound_ok :
        asset_source_status == 0 ? grid :
        asset_source_status == -1 ? sound_fail : source_missing;
    vh_canvas_fill_rect(canvas, 1000, 219, 130, 18, source_color);
    /* Distinct audout liveness marker: green means at least 16 actual
     * SEQ/SPU/resampler blocks produced AND audoutPlayBuffer returned;
     * amber means initialized but no such progress yet. This proves
     * software/service advancement, NOT audible output from speakers. */
    const unsigned pcm_blocks = atomic_load(&pcm_blocks_generated);
    const unsigned returned_buffers = atomic_load(&audout_buffers_completed);
    const uint32_t pipeline_color =
        !healthy ? sound_fail :
        (pcm_blocks >= 16u && returned_buffers >= 16u)
        ? sound_ok : source_missing;
    vh_canvas_fill_rect(canvas, 1000, 270, 130, 24, pipeline_color);
    /* Separate synthetic-only proof that the audio-owner has switched
     * scenes at least twice while PCM pages continued to return. This
     * is a software transition counter, never an audible-audio claim.
     * Neutral gray for user files and incomplete/error sources.
     */
    const unsigned scene_switches=atomic_load(&synthetic_scene_switches);
    const uint32_t switch_color=asset_source_status != 0 ? grid :
        !healthy ? sound_fail :
        (scene_switches >= 2u &&
         returned_buffers >= 128u) ? sound_ok : source_missing;
    vh_canvas_fill_rect(canvas,1000,325,130,18,switch_color);
#ifdef VH_AUDIO_GUEST_ZR_AUTOTEST
    /* CI-only guest witness: this distinct tile becomes GREEN only
     * AFTER the real audout descriptor returns following one fake
     * pre-service ZR failure, recovery and PCM/music-state checks.
     * The pixel is proof of guest-software evidence, NOT sound. */
    const int zr=atomic_load(&guest_zr_witness);
    const uint32_t zr_color=zr<0 || !healthy ? sound_fail :
        zr==2 && returned_buffers>=32u &&
        atomic_load(&audout_failed_returns)>=1u
        ? sound_ok : source_missing;
    vh_canvas_fill_rect(canvas,1000,455,130,24,zr_color);
#endif
#ifdef VH_AUDIO_GUEST_ZL_AUTOTEST
    /* A GREEN tile is not healthy playback: it explicitly certifies
     * fail-closed handling of an invalid clock AFTER an exact returned
     * PCM descriptor. The ordinary service tile is RED by design. */
    const int zl=atomic_load(&guest_zl_witness);
    const uint32_t zl_color=zl<0 ? sound_fail :
        zl==2 && atomic_load(&audio_fault)==10 &&
        returned_buffers==16u &&
        atomic_load(&audout_failed_returns)==0u
        ? sound_ok : source_missing;
    vh_canvas_fill_rect(canvas,1000,510,130,26,zl_color);
#endif
#if defined(VH_AUDIO_GUEST_RESUME_AUTOTEST) || defined(VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST)
    /* GREEN only after BOTH serial device operations and a subsequent
     * exact PCM return after each; not a real HOME/sleep notification. */
    const int resume=atomic_load(&guest_resume_witness);
    const uint32_t resume_color=resume<0 || !healthy ? sound_fail :
        resume==4 && returned_buffers>=33u &&
        atomic_load(&audout_failed_returns)==0u
        ? sound_ok : source_missing;
    vh_canvas_fill_rect(canvas,1000,555,130,26,resume_color);
#ifdef VH_AUDIO_GUEST_RESUME_RETRY_AUTOTEST
    /* A separate marker distinguishes this failed first open from a
     * clean X/Y roundtrip. The normal marker is also required. */
    const uint32_t retry_color=resume==4 && healthy &&
        returned_buffers>=33u ? sound_ok :
        resume<0 || !healthy ? sound_fail : source_missing;
    vh_canvas_fill_rect(canvas,1150,555,90,26,retry_color);
#endif
#endif
    /* BLUE: peak sum of audout service waits on normal PCM pages.
     * LIGHT BLUE: the very first page after a synthetic SEQ switch.
     * Both gauges cap at four nominal source-block durations.
     * Timing can include multiple audout submissions after recovery,
     * but not service stop/reopen. Slow calls are not glitch proof.
     * Telemetry comes from the audio thread via atomics.
     */
    const unsigned peak_wait_us=atomic_load(&audout_wait_peak_us);
    const unsigned slow_waits=atomic_load(&audout_waits_longer_than_page);
    const unsigned failed_returns=atomic_load(&audout_failed_returns);
    const unsigned page_us=VH_AUDIO_BLOCK_FRAMES*1000000u/
                           VH_AUDIO_SAMPLE_RATE;
    const unsigned max_display=page_us*4u;
    const unsigned clamped=peak_wait_us>max_display
        ? max_display : peak_wait_us;
    const int wait_width=(int)((uint64_t)clamped*130u/max_display);
    vh_canvas_fill_rect(canvas,1000,375,130,12,grid);
    vh_canvas_fill_rect(canvas,1000,375,wait_width,12,hero);
    const unsigned switch_count=atomic_load(&audout_switch_pages_recorded);
    const unsigned switch_peak=atomic_load(&audout_switch_page_peak_us);
    const unsigned boundary_clamped=switch_peak>max_display
        ? max_display : switch_peak;
    const int boundary_width=(int)((uint64_t)boundary_clamped*130u/
                                   max_display);
    vh_canvas_fill_rect(canvas,1000,399,130,12,grid);
    if (!using_user_files && switch_count) {
        vh_canvas_fill_rect(canvas,1000,399,boundary_width,12,
                            RGBA8_MAXALPHA(158,198,246));
    }
    /* Distinct counters are sampled even when not rendered as text:
     * a warning is not derived from slow waits alone, since the
     * blocking API can normally wait for a page to finish playing.
     */
    (void)slow_waits;
    (void)failed_returns;
    /* Animated heartbeat proves video continues while audout worker runs. */
    vh_canvas_fill_rect(canvas, 70, 610, 800, 14, grid);
    vh_canvas_fill_rect(canvas, 70, 610, 20 + (int)(frame % 780u), 14, hero);
#ifdef VH_AUDIO_HARDWARE_FOCUS_TRACE
    /* N B F P R: notification mode, HOME-background, foreground
     * return, post-returned-PCM, OnResume signal. Blue means the
     * indicated EVENT was observed, NOT that audio was heard.
     * Keep these away from synthetic ZL/ZR/resume witness tiles. */
    const unsigned backgrounds=atomic_load(&hardware_focus_backgrounds);
    const unsigned focus_returns=atomic_load(&hardware_focus_returns);
    const unsigned applet_resumes=atomic_load(&hardware_focus_resumes);
    const unsigned pages=atomic_load(&audout_buffers_completed);
    const unsigned at_return=atomic_load(&hardware_focus_pages_at_return);
    const int notify_mode=atomic_load(&hardware_focus_notify_mode);
    const uint32_t focus_colors[5]={
        notify_mode>0 ? hero : sound_fail,
        backgrounds>0u ? hero : source_missing,
        focus_returns>0u ? hero : source_missing,
        focus_returns>0u && pages>at_return ? hero : source_missing,
        applet_resumes>0u ? hero : source_missing
    };
    for(unsigned focus_tile=0;focus_tile<5u;focus_tile++)
        vh_canvas_fill_rect(canvas,1000+(int)focus_tile*48,
                            635,40,26,focus_colors[focus_tile]);
#endif
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

    /* Mount SD explicitly if the libnx runtime has not done so.
     * Never claim that all music files are missing when the filesystem
     * itself could not be opened. Mount ownership determines cleanup. */
    const int sdmc_previously_mounted =
        fsdevGetDeviceFileSystem("sdmc") != NULL;
    int sdmc_ready = sdmc_previously_mounted;
    if (!sdmc_ready && R_SUCCEEDED(fsdevMountSdmc())) {
        sdmc_mounted_here = 1;
        sdmc_ready = 1;
    }
    const int music_ready = sdmc_ready && prepare_music(&using_user_files) == 0;
    asset_source_status = !sdmc_ready ? -2 :
                          !music_ready ? -1 :
                          using_user_files ? 1 : 0;
#ifdef VH_AUDIO_HARDWARE_FOCUS_TRACE
    /* Diagnostic NRO only: request delivery of actual focus changes
     * during HOME/sleep while preserving the system's suspend policy.
     * Register before entering the libnx appletMainLoop. All callback
     * mutations are atomic counters. No audout IPC from the callback. */
    appletHook(&hardware_focus_cookie,hardware_focus_event,NULL);
    const Result notify_rc=appletSetFocusHandlingMode(
        AppletFocusHandlingMode_SuspendHomeSleepNotify);
    atomic_store(&hardware_focus_notify_mode,
                 R_SUCCEEDED(notify_rc) ? 1 : -1);
#endif
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
#ifdef VH_AUDIO_HARDWARE_FOCUS_TRACE
    appletUnhook(&hardware_focus_cookie);
#endif
    /* The worker is fully joined before bank PCM can be released. */
    vh_audio_assets_close(&user_assets);
    if (sdmc_mounted_here) (void)fsdevUnmountDevice("sdmc");
    framebufferClose(&framebuffer);
    return 0;
}
