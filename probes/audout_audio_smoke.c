/* Native libnx audout proof: no SDL2 package or internet dependency.
 * Tries local, user-owned music.seq/.vh/.vb; otherwise synthetic fixtures.
 * PS1 SEQ runs at 44.1 kHz; output is linearly resampled to audout 48 kHz.
 * Console audio output and actual game compatibility remain unverified
 * until this NRO is exercised on a physical Switch.
 */
#include <switch.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* A source-revision label for screenshot provenance, not an NRO hash.
 * Git-less/modified builds must be explicit rather than look verified. */
#ifndef VH_AUDIO_BUILD_REV
#define VH_AUDIO_BUILD_REV "UNKNOWN"
#endif
#ifndef VH_AUDIO_BUILD_STATUS
#define VH_AUDIO_BUILD_STATUS "NO-GIT"
#endif

#include "vh_audio_assets.h"
#include "vh_audio_resample.h"
#include "vh_audio_output_recovery.h"
#include "vh_audio_listening_marks.h"
#include "vh_audio_mark_buttons.h"
#include "vh_audio_listener_input.h"
#include "vh_audio_input_poll.h"
#include "vh_audio_report_pages.h"
#include "vh_audio_compute_timing.h"
#include "vh_audio_compute_wait_join.h"
#include "vh_audio_page_telemetry.h"
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#define LOCAL_AUDIO_DIR "sdmc:/switch/vandal-hearts-remake/audio"
#define MAX_PROBE_BLOCKS 3600u
#define SYNTHETIC_SCENE_BLOCKS 64u

static VhAudioAssets user_assets;
static VhNativeVab synthetic_bank;
static VhNativeSeq seq;
static VhNativeSpu synth;
static VhAudioResample resampler;
/* The applet hook ONLY records lifecycle messages. It is invoked while
 * appletMainLoop processes events; no audio callback or PCM mutation. */
static VhAudioAppletEvents focus_events;
static unsigned focus_record_errors;
/* 0: unsupported applet context; 1: enabled; 2: request rejected. */
static unsigned focus_notification_mode;
static void audio_applet_hook(AppletHookType hook,void *param) {
    (void)param;
    unsigned event=0u;
    if(hook==AppletHookType_OnFocusState) {
        const AppletFocusState state=appletGetFocusState();
        if(state==AppletFocusState_Background)
            event=VH_AUDIO_APPLET_BACKGROUND;
        else if(state==AppletFocusState_InFocus)
            event=VH_AUDIO_APPLET_FOREGROUND;
    } else if(hook==AppletHookType_OnResume) {
        event=VH_AUDIO_APPLET_RESUME;
    }
    if(event && vh_audio_applet_record_at(
                      &focus_events,event,armGetSystemTick()))
        ++focus_record_errors;
}
/* Snapshot never appears in the device callback or PCM output path. */
static VhNativeSpu manual_spu_snapshot;

static uint8_t fixture_vh[32u + 128u*16u + 512u + 512u];
static uint8_t fixture_vb[48];
static int16_t fixture_pcm[56];

static int16_t in_44100[VH_AUDIO_BLOCK_FRAMES * 2u];
/* libnx AudioOutBuffer.buffer_size advertises a full 0x1000 page,
 * not merely the active 640 stereo frames. Back it with that entire
 * aligned page so audout never sees an undersized memory mapping.
 */
static int16_t out_48000[0x1000u / sizeof(int16_t)]
    __attribute__((aligned(0x1000)));

/* In-memory fingerprint only; no audio samples are exported. */
static uint64_t pcm_page_fingerprint(const int16_t *page,size_t frames) {
    uint64_t hash=UINT64_C(1469598103934665603);
    for(size_t i=0u;i<frames*2u;i++) {
        hash^=(uint16_t)page[i];
        hash*=UINT64_C(1099511628211);
    }
    return hash;
}

static const uint8_t fixture_seq[] = {
    'p','Q','E','S',0,0,0,0, 0x01,0xe0,0x07,0xa1,0x20,0,0,
    0,0xc0,7, 0,0xb0,7,127, 0,0xb0,10,64,
    0,0x90,60,110, 0x81,0x70,0x80,60,0,
    0x81,0x70,0xff,0x2f,
};
/* Alternating fixture only; user-supplied SEQ/VH/VB is NEVER
 * switched automatically by this console diagnostic. */
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

/* All device callbacks run on the single probe audio producer thread.
 * A failed audoutPlayBuffer keeps the immutable 48-kHz page in out_48000;
 * reopening the service must not re-run SEQ, SPU or the resampler.
 */
typedef struct {
    AudioOutBuffer page;
    VhAudioSubmitTiming timing;
    VhAudioSceneWaits scene_waits;
    VhAudioPageLease lease;
    VhAudioTransportTimingHealth transport_health;
    int initialized;
    int started;
} NativeOutput;

static void native_close(void *opaque) {
    NativeOutput *dev=opaque;
    /* Close only after a confirmed stop AND PCM descriptor release.
     * A direct/misordered callback must never tear down active audout. */
    if (!dev->initialized || dev->started ||
        !vh_audio_page_lease_ready(&dev->lease))
        return;
    audoutExit();
    dev->initialized=0;
    dev->started=0;
}
static int native_open(void *opaque) {
    NativeOutput *dev=opaque;
    if (dev->initialized || !vh_audio_page_lease_ready(&dev->lease) ||
        R_FAILED(audoutInitialize())) return -1;
    dev->initialized=1;
    if (audoutGetSampleRate()!=VH_NATIVE_AUDOUT_RATE ||
        audoutGetChannelCount()!=2u ||
        audoutGetPcmFormat()!=PcmFormat_Int16) {
        native_close(dev);
        return -1;
    }
    memset(&dev->page,0,sizeof dev->page);
    dev->page.buffer=out_48000;
    dev->page.buffer_size=sizeof out_48000;
    return dev->page.buffer_size==0x1000u ? 0 : -1;
}
static int native_start(void *opaque) {
    NativeOutput *dev=opaque;
    if (!dev->initialized || dev->started ||
        !vh_audio_page_lease_ready(&dev->lease) ||
        R_FAILED(audoutStartAudioOut())) return -1;
    dev->started=1;
    return 0;
}
static int native_stop(void *opaque) {
    NativeOutput *dev=opaque;
    /* A stopped service with an outstanding page is contradictory:
     * never authorize closing or reusing its backing memory. */
    if (!dev->started)
        return vh_audio_page_lease_ready(&dev->lease) ? 0 : -1;
    /* The exact service stop result controls the lease. A failed
     * stop cannot authorize reuse, restart or a music scene switch. */
    const Result rc=audoutStopAudioOut();
    if (vh_audio_page_lease_stopped(&dev->lease,
                                  R_SUCCEEDED(rc) ? 0 : -1))
        return -1;
    dev->started=0;
    return 0;
}
static int native_submit(void *opaque,const int16_t *pcm,size_t frames) {
    NativeOutput *dev=opaque;
    if (!dev->initialized || !dev->started ||
        pcm!=out_48000 || frames==0 ||
        frames>VH_AUDIO_RESAMPLE_MAX_FRAMES) return -1;
    /* Reserve BEFORE updating the descriptor: even its metadata must
     * stay unchanged if a previous attempt remains in flight. */
    if (vh_audio_page_lease_begin(&dev->lease,&dev->page))
        return -1;
    dev->page.data_size=frames*2u*sizeof(int16_t);
    AudioOutBuffer *returned=NULL;
    /* Measure actual blocking service time (one invocation, including
     * failed attempts), separately from the pre-render DSP budget. */
    const uint64_t before=armGetSystemTick();
    const Result rc=audoutPlayBuffer(&dev->page,&returned);
    const uint64_t elapsed=armGetSystemTick()-before;
    const int accepted=R_SUCCEEDED(rc) &&
        vh_audio_output_page_returned(&dev->page,returned);
    /* The exact returned descriptor releases this page. A failed
     * attempt retains its lease until recovery confirms audoutStop. */
    if (accepted && vh_audio_page_lease_return(&dev->lease,returned))
        return -1;
    const int timing_result=vh_audio_output_record_submit_timing(
            &dev->timing,elapsed,armGetSystemTickFreq(),frames,accepted);
    /* A valid returned descriptor is already consumed by the device.
     * Timing overflow/invalid clock must NOT force a second submission.
     * Mark telemetry invalid, then abort analysis on the producer thread
     * without a transport recovery attempt for this delivered PCM. */
    return vh_audio_output_transport_outcome(
               accepted,timing_result,&dev->transport_health);
}

/* Each report screen is deliberately short enough for a single
 * photograph of the Nintendo Switch framebuffer console. Called
 * only after stopped audout and released SD music assets.
 */
typedef struct {
    const NativeOutput *output;
    const VhAudioManualResume *manual;
    const VhAudioAppletEvents *focus;
    unsigned focus_errors;
    const VhAudioOutputRecovery *recovery;
    const VhAudioPcmSeams *seams;
    const VhAudioListeningMarks *marks;
    const VhAudioInputPoll *poll;
    const VhAudioMarkButtons *buttons;
    const VhAudioComputeTiming *compute;
    const VhAudioComputeWaitJoin *compute_wait;
    int compute_evidence;
    uint64_t tick_frequency;
    unsigned played, switched, user_files;
    int result, seam_evidence, tail_evidence, listen_evidence, poll_evidence;
    unsigned verdict;
} VhAudioProbeReport;

static void vh_audio_show_report(const VhAudioProbeReport *r,
                                 unsigned page) {
    const VhAudioPageWaitBucket *n=&r->output->scene_waits.ordinary;
    const VhAudioPageWaitBucket *s=&r->output->scene_waits.first_after_switch;
    const VhAudioPcmSeams *pcm=r->seams;
    const VhAudioListeningMarks *marks=r->marks;
    const VhAudioInputPoll *poll=r->poll;
    const uint64_t hz=r->tick_frequency;
    consoleClear();
    printf("VH audout / %.12s [%s]\n",
           VH_AUDIO_BUILD_REV,VH_AUDIO_BUILD_STATUS);
    if (page==0u) {
        printf("REPORT 1/4: DEVICE / SERVICE\n\n");
        printf("Source: %s\n",r->user_files ? "user SD music" : "generated fixture");
        printf("Result=%d  PCM accounting=%s\n",r->result,
               r->verdict==VH_AUDIO_REPORT_FULL ? "FULL" :
               r->verdict==VH_AUDIO_REPORT_INCOMPLETE ? "INCOMPLETE" :
                                                       "INVALID");
        printf("Pages %u/%u, fixture switches=%u\n",
               r->played,MAX_PROBE_BLOCKS,r->switched);
        printf("Backend=%llu fail=%llu untimed=%llu timing=%s\n",
               (unsigned long long)r->output->timing.calls,
               (unsigned long long)r->output->timing.failed_submissions,
               (unsigned long long)r->output->transport_health.delivered_without_timing,
               r->output->transport_health.timing_fault ? "INVALID" : "VALID");
        printf("Peak wait=%llu us; >page calls=%llu\n",
               (unsigned long long)vh_audio_output_ticks_to_us(
                   r->output->timing.max_ticks,hz),
               (unsigned long long)r->output->timing.waits_longer_than_page);
        printf("Restarts=%u recovered=%u\n",
               r->recovery->restart_attempts,r->recovery->recoveries);
        printf("X stop/start %u/%u  Y reopen %u/%u\n",
               r->manual->quick_ok,r->manual->quick_attempts,
               r->manual->reopen_ok,r->manual->reopen_attempts);
        printf("X/Y audit=%s ignored=%u unsafe=%u mismatch=%u\n",
               vh_audio_manual_verify(r->manual)==0 ? "VALID" : "INVALID",
               r->manual->ignored_chords,r->manual->unsafe_requests,
               r->manual->state_mismatches);
        const uint64_t rendered=r->compute->rendered_pages;
        const uint64_t total_us=vh_audio_output_ticks_to_us(
            r->compute->total_ticks,hz);
        printf("DSP avg/peak: %llu / %llu us\n",
               (unsigned long long)(rendered?total_us/rendered:0u),
               (unsigned long long)vh_audio_output_ticks_to_us(
                   r->compute->max_ticks,hz));
        printf("DSP >budget=%llu; rendered=%llu\n",
               (unsigned long long)r->compute->over_budget,
               (unsigned long long)rendered);
        printf("DSP overbudget normal/switch=%llu/%llu\n",
               (unsigned long long)r->compute->ordinary.over_budget,
               (unsigned long long)r->compute->first_after_switch.over_budget);
        printf("DSP peak normal/switch=%llu/%llu us\n",
               (unsigned long long)vh_audio_output_ticks_to_us(
                   r->compute->ordinary.max_ticks,hz),
               (unsigned long long)vh_audio_output_ticks_to_us(
                   r->compute->first_after_switch.max_ticks,hz));
        printf("DSP scene audit=%s; switch renders=%llu\n",
               r->compute_evidence==0 ? "VALID" : "INVALID",
               (unsigned long long)r->compute->first_after_switch.rendered_pages);
        printf("Both DSP>budget and audout>2x N/S=%llu/%llu\n",
               (unsigned long long)r->compute_wait->ordinary.both_over_2x,
               (unsigned long long)r->compute_wait->first_after_switch.both_over_2x);
        printf("Both DSP>budget and audout>4x N/S=%llu/%llu\n",
               (unsigned long long)r->compute_wait->ordinary.both_over_4x,
               (unsigned long long)r->compute_wait->first_after_switch.both_over_4x);
        printf("DSP overbudget by wait bin (<=1 1-2 2-4 >4):\n");
        printf("Normal: %llu %llu %llu %llu\n",
               (unsigned long long)r->compute_wait->ordinary.dsp_over_in_band[0],
               (unsigned long long)r->compute_wait->ordinary.dsp_over_in_band[1],
               (unsigned long long)r->compute_wait->ordinary.dsp_over_in_band[2],
               (unsigned long long)r->compute_wait->ordinary.dsp_over_in_band[3]);
        printf("Switch: %llu %llu %llu %llu\n",
               (unsigned long long)r->compute_wait->first_after_switch.dsp_over_in_band[0],
               (unsigned long long)r->compute_wait->first_after_switch.dsp_over_in_band[1],
               (unsigned long long)r->compute_wait->first_after_switch.dsp_over_in_band[2],
               (unsigned long long)r->compute_wait->first_after_switch.dsp_over_in_band[3]);
        printf("Wait bins: <=1x <=2x <=4x >4x\n");
        printf("Normal: %llu %llu %llu %llu\n",
               (unsigned long long)n->wait_le_page,
               (unsigned long long)n->wait_le_2pages,
               (unsigned long long)n->wait_le_4pages,
               (unsigned long long)n->wait_gt_4pages);
        printf("Switch: %llu %llu %llu %llu\n",
               (unsigned long long)s->wait_le_page,
               (unsigned long long)s->wait_le_2pages,
               (unsigned long long)s->wait_le_4pages,
               (unsigned long long)s->wait_gt_4pages);
        printf("Service delay alone is NOT an audible glitch.\n");
    } else if (page==1u) {
        printf("REPORT 2/4: PCM SEAMS / COUNTS\n\n");
        printf("Seam audit=%s; pages=%llu\n",
               r->seam_evidence ? "INVALID" : "VALID",
               (unsigned long long)pcm->delivered_pages);
        printf("Last returned PCM / A-B ring=%s\n",
               r->tail_evidence ? "INVALID" : "VALID");
        printf("Bins: <=1x <=2x <=4x >4x\n");
        printf("Normal seam counts: %llu %llu %llu %llu\n",
               (unsigned long long)pcm->ordinary.count[0],
               (unsigned long long)pcm->ordinary.count[1],
               (unsigned long long)pcm->ordinary.count[2],
               (unsigned long long)pcm->ordinary.count[3]);
        printf("Switch seam counts: %llu %llu %llu %llu\n",
               (unsigned long long)pcm->first_after_switch.count[0],
               (unsigned long long)pcm->first_after_switch.count[1],
               (unsigned long long)pcm->first_after_switch.count[2],
               (unsigned long long)pcm->first_after_switch.count[3]);
        printf("Peak PCM16 seam, normal:\n%u %u %u %u\n",
               pcm->ordinary.peak_abs_step[0],
               pcm->ordinary.peak_abs_step[1],
               pcm->ordinary.peak_abs_step[2],
               pcm->ordinary.peak_abs_step[3]);
        printf("Peak PCM16 seam, switch:\n%u %u %u %u\n",
               pcm->first_after_switch.peak_abs_step[0],
               pcm->first_after_switch.peak_abs_step[1],
               pcm->first_after_switch.peak_abs_step[2],
               pcm->first_after_switch.peak_abs_step[3]);
        printf("Failed logical pages (normal/switch): %llu/%llu\n",
               (unsigned long long)n->failed_pages,
               (unsigned long long)s->failed_pages);
        printf("First delivered page wait bin: %u (0..3)\n",
               pcm->first_wait_band);
        printf("PCM boundary step is NOT proof of a click.\n");
    } else if (page==2u) {
        printf("REPORT 3/4: HUMAN A / NORMAL B / ALL\n\n");
        printf("Windows: A=%llu B=%llu all=%llu\n",
               (unsigned long long)marks->manual_marks,
               (unsigned long long)marks->control_marks,
               (unsigned long long)marks->returned_pages);
        printf("Event overlaps: A / B / all\n");
        printf("Cue change: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_switch,
               (unsigned long long)marks->controls_near_switch,
               (unsigned long long)marks->windows_near_switch);
        printf(">2x wait: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_wait_over_2x,
               (unsigned long long)marks->controls_near_wait_over_2x,
               (unsigned long long)marks->windows_near_wait_over_2x);
        printf(">4x wait: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_wait_over_4x,
               (unsigned long long)marks->controls_near_wait_over_4x,
               (unsigned long long)marks->windows_near_wait_over_4x);
        printf("Retry: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_retry,
               (unsigned long long)marks->controls_near_retry,
               (unsigned long long)marks->windows_near_retry);
        printf("DSP>budget: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_dsp_over,
               (unsigned long long)marks->controls_near_dsp_over,
               (unsigned long long)marks->windows_near_dsp_over);
        printf("DSP & wait>2x: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_dsp_wait_over_2x,
               (unsigned long long)marks->controls_near_dsp_wait_over_2x,
               (unsigned long long)marks->windows_near_dsp_wait_over_2x);
        printf("DSP & wait>4x: %llu / %llu / %llu\n",
               (unsigned long long)marks->marks_near_dsp_wait_over_4x,
               (unsigned long long)marks->controls_near_dsp_wait_over_4x,
               (unsigned long long)marks->windows_near_dsp_wait_over_4x);
        printf("Peak PCM16 near A/B=%u/%u\n",
               marks->peak_seam_near_mark,
               marks->peak_seam_near_control);
        printf("Max A poll gap=%llu us\n",
               (unsigned long long)vh_audio_output_ticks_to_us(
                   poll->max_gap_ticks,hz));
        printf("Long polls >1x/>4x: %llu/%llu\n",
               (unsigned long long)poll->gaps_over_page,
               (unsigned long long)poll->gaps_over_4pages);
        printf("A/B chord attempts ignored=%llu\n",
               (unsigned long long)r->buttons->rejected_chords);
        printf("A polls=%llu; mark/poll audit=%s/%s\n",
               (unsigned long long)poll->samples,
               r->listen_evidence ? "INVALID" : "VALID",
               r->poll_evidence ? "INVALID" : "VALID");
        printf("Release both A/B before the next annotation.\n");
        printf("B control is not unbiased sampling.\n");
        printf("Short taps missed; zero A != no glitches.\n");
    } else {
        printf("REPORT 4/4: HOME / RETURNED PCM\n\n");
        printf("Git source: %s [%s]\n",
               VH_AUDIO_BUILD_REV,VH_AUDIO_BUILD_STATUS);
        printf("Source: %s\n",r->user_files ? "user SD music" : "generated fixture");
        printf("Result=%d PCM accounting=%s\n",r->result,
               r->verdict==VH_AUDIO_REPORT_FULL ? "FULL" :
               r->verdict==VH_AUDIO_REPORT_INCOMPLETE ? "INCOMPLETE" :
                                                       "INVALID");
        printf("HOME bg/returns=%u/%u OnResume=%u\n",
               r->focus->backgrounds,r->focus->returns,r->focus->resumes);
        printf("Focus events duplicate/error=%u/%u\n",
               r->focus->ignored_duplicates,r->focus_errors);
        printf("First PCM after HOME=%u pending=%u merged=%u\n",
               r->focus->first_pages_after_return,
               r->focus->pending_return,r->focus->coalesced_returns);
        printf("Audout returned pages observed=%u\n",
               r->focus->returned_pages);
        printf("HOME timed returns=%u avg/peak=%llu/%llu us\n",
               r->focus->timed_first_pages,
               (unsigned long long)(r->focus->timed_first_pages
                 ? vh_audio_output_ticks_to_us(
                     r->focus->total_page_gap_ticks,hz)/
                     r->focus->timed_first_pages : 0u),
               (unsigned long long)vh_audio_output_ticks_to_us(
                     r->focus->max_page_gap_ticks,hz));
        printf("HOME lag bins <=1/2/4/>4x: %u/%u/%u/%u\n",
               r->focus->page_budget_bands[0],
               r->focus->page_budget_bands[1],
               r->focus->page_budget_bands[2],
               r->focus->page_budget_bands[3]);
        printf("HOME banded/timed=%u/%u (unknown excluded)\n",
               r->focus->budgeted_first_pages,
               r->focus->timed_first_pages);
        printf("Undelivered submits all/pending=%u/%u\n",
               r->focus->failed_logical_submissions,
               r->focus->failures_while_pending);
        printf("HOME focus notify=%s\n",
               focus_notification_mode==1u ? "ENABLED" :
               focus_notification_mode==2u ? "UNAVAILABLE" : "APPLET MODE");
        printf("HOME observed, audible resume UNVERIFIED\n");
        printf("Returned PCM does NOT prove audible sound.\n");
    }
    printf("\nLEFT/RIGHT change page; PLUS exit.\n");
    printf("No audio recorded; inspect on real Switch.\n");
    consoleUpdate(NULL);
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    consoleInit(NULL);
    printf("Vandal Hearts - native libnx audout probe\n");
    printf("SEQ/VAB/SPU at 44100 -> audout at 48000 Hz\n");
    consoleUpdate(NULL);

    int user_files=0;
    if (prepare_music(&user_files) != 0) {
        printf("Invalid/missing portion of local SEQ/VH/VB set.\n");
        consoleUpdate(NULL);
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 1;
    }
    printf("Source: %s\n", user_files ? "user-owned SD files" : "synthetic");
    if (!user_files)
        printf("Fixture changes every %u returned PCM pages; SD music unchanged\n",
               SYNTHETIC_SCENE_BLOCKS);
    printf("A = perceived audio defect; B = sounds normal (control).\n");
    printf("Release BOTH A/B between marks; held chords ignored.\n");
    printf("X: pause/start; Y: stop/reopen/start (after PCM return).\n");
    printf("HOME is a separate physical-console test, not counted as X/Y.\n");
    printf("These are manual tags, never automatic glitch detection.\n");
    consoleUpdate(NULL);
    padConfigureInput(1,HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    NativeOutput output={0};
    VhAudioOutputRecovery recovery={0};
    VhAudioPcmSeams seam_stats={0};
    VhAudioListeningMarks listening_marks={0};
    VhAudioMarkButtons mark_buttons={0};
    VhAudioInputPoll input_poll={0};
    VhAudioManualResume manual_resume={0};
    const VhAudioOutputOps ops={
        &output,native_submit,native_stop,native_close,native_open,native_start
    };
    if (native_open(&output) || native_start(&output)) {
        printf("audout initialization or format negotiation failed\n");
        /* A failed stop leaves a possibly outstanding audout page.
         * Never call audoutExit until the stop callback succeeded. */
        if (vh_audio_output_stop_close(&ops))
            printf("audout stop unconfirmed; close skipped\n");
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 2;
    }

    /* Application launches may request HOME/sleep focus messages.
     * The default applet mode does not guarantee these notifications:
     * show the mode explicitly rather than inventing HOME attempts.
     * Never alter suspend behavior in library-applet (hbmenu) mode. */
    if(appletGetAppletType()==AppletType_Application) {
        const Result focus_rc=appletSetFocusHandlingMode(
                       AppletFocusHandlingMode_SuspendHomeSleepNotify);
        focus_notification_mode=R_SUCCEEDED(focus_rc) ? 1u : 2u;
    }
    /* Observe real HOME/sleep focus notifications, not just X/Y.
     * The hook never manipulates audout or renders PCM. */
    AppletHookCookie focus_cookie={0};
    appletHook(&focus_cookie,audio_applet_hook,NULL);

    /* System ticks measure SEQ + DSP + 48k conversion, excluding
     * audoutPlayBuffer wait and console updates. */
    const uint64_t tick_frequency = armGetSystemTickFreq();
    const uint64_t block_budget_ticks =
        tick_frequency * VH_AUDIO_BLOCK_FRAMES / VH_AUDIO_SAMPLE_RATE;
    VhAudioComputeTiming compute={0};
    VhAudioComputeWaitJoin compute_wait={0};
    unsigned played_blocks = 0;
    unsigned fixture_b = 0, completed_switches = 0;
    int result = 0;
    while (appletMainLoop() && played_blocks < MAX_PROBE_BLOCKS) {
        const uint64_t tick_begin = armGetSystemTick();
        unsigned switched_this_block=0;
        /* The previous blocking audout call returned its exact page
         * before this loop iteration, and no old PCM page is queued.
         * Never switch a user-owned SD music set automatically.
         */
        if (!vh_audio_page_lease_ready(&output.lease)) {
            result=20; /* outstanding device page; cannot switch/render */
            break;
        }
        if (!user_files && played_blocks &&
            played_blocks%SYNTHETIC_SCENE_BLOCKS==0u) {
            const uint8_t *next=fixture_b ? fixture_seq : fixture_seq_b;
            const size_t next_size=fixture_b
                ? sizeof(fixture_seq) : sizeof(fixture_seq_b);
            if (vh_native_seq_switch_scene(&seq,next,next_size,&synth,
                                           vh_native_vab_resolve,
                                           &synthetic_bank,0)) {
                result=8;
                break;
            }
            fixture_b^=1u;
            switched_this_block=1u;
        }
        if (vh_native_seq_advance_block(&seq) < 0) {
            result = 5;
            break;
        }
        vh_native_spu_render(&synth, in_44100, VH_AUDIO_BLOCK_FRAMES);
        const size_t count = vh_audio_resample_process(
            &resampler, in_44100, VH_AUDIO_BLOCK_FRAMES,
            out_48000, VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if (!count || count * 2u * sizeof(int16_t) > sizeof(out_48000)) {
            result = 6;
            break;
        }
        const uint64_t elapsed_ticks = armGetSystemTick() - tick_begin;
        if (vh_audio_compute_record(&compute,elapsed_ticks,
                                    block_budget_ticks,
                                    switched_this_block)) {
            result=16;
            break;
        }
        /* Retry the same fully rendered page after a bounded backend
         * restart. A failed output must not advance any music clock.
         */
        const VhAudioSubmitTiming before_submit=output.timing;
        const int submit_result=vh_audio_output_submit_recover(
            &ops,&recovery,out_48000,count);
        if (output.transport_health.timing_fault) {
            /* No retry here: if the service already returned the exact
             * page, submit_result==0 correctly means delivered. The
             * telemetry is incomplete, so fail evidence instead of
             * calling audoutPlayBuffer again on the same PCM. */
            result=28;
            break;
        }
        if (submit_result) {
            /* A terminally undelivered logical page has no PCM seam,
             * no A/B ring entry, and no returned-page joint event. */
            if (vh_audio_output_record_scene_page(
                    &output.scene_waits,&before_submit,&output.timing,
                    tick_frequency,count,(int)switched_this_block,0)) {
                result=9;
                break;
            }
            /* No returned descriptor or PCM telemetry on this path.
             * Keep any observed HOME return pending until a later
             * successful page, even if recovery needs explicit retry. */
            if (vh_audio_applet_submit_failed(&focus_events)) {
                ++focus_record_errors;
                result=27;
                break;
            }
            result=7;
            break;
        }
        /* One returned page updates four telemetry views as a single
         * all-or-nothing transaction. Every later read sees identical
         * page clocks; no additional audio or controller polling. */
        if (vh_audio_returned_page_telemetry_record(
                &output.scene_waits,&seam_stats,
                &compute_wait,&listening_marks,
                out_48000,count,switched_this_block,
                &before_submit,&output.timing,tick_frequency,
                (unsigned)(elapsed_ticks>block_budget_ticks))) {
            result=18;
            break;
        }
        ++played_blocks;
        completed_switches+=switched_this_block;
        /* Commit the first returned descriptor after a real foreground
         * notification. HOME events without this observation are NOT
         * treated as proof of device playback or audible output. */
        const uint64_t page_ticks=
            (uint64_t)count*tick_frequency/VH_NATIVE_AUDOUT_RATE;
        if(vh_audio_applet_page_returned_budget_at(
                   &focus_events,armGetSystemTick(),page_ticks)<0) {
            ++focus_record_errors;
            result=25;
            break;
        }
        /* Read A-button rising edge only after audout has returned
         * its PCM descriptor; do not touch SEQ, SPU or resampler. */
        padUpdate(&pad);
        const uint64_t sample_tick=armGetSystemTick();
        if (vh_audio_input_poll_record(&input_poll,sample_tick,page_ticks)) {
            result=14;
            break;
        }
        /* Manual on-device pause/reopen probes run ONLY after the
         * previous audoutPlayBuffer returned the exact descriptor.
         * X: ordinary stop/start. Y: stop then forced reopen.
         * Actual HOME/suspend remains observational; applet callback
         * does not manipulate audout or attempt automatic recovery.
         * Never do device work from a controller/app hook callback. */
        const uint64_t pressed=padGetButtonsDown(&pad);
        const uint64_t held=padGetButtons(&pad);
        const unsigned manual_pressed=
            (pressed&HidNpadButton_X ? VH_AUDIO_MANUAL_X : 0u) |
            (pressed&HidNpadButton_Y ? VH_AUDIO_MANUAL_Y : 0u);
        const unsigned manual_held=
            (held&HidNpadButton_X ? VH_AUDIO_MANUAL_X : 0u) |
            (held&HidNpadButton_Y ? VH_AUDIO_MANUAL_Y : 0u);
        const unsigned manual_action=vh_audio_manual_select(
                                                 manual_pressed,manual_held);
        if(manual_action==VH_AUDIO_MANUAL_IGNORE) {
            ++manual_resume.ignored_chords;
        } else if(manual_action) {
            const int reopen=manual_action==VH_AUDIO_MANUAL_Y;
            if(reopen) ++manual_resume.reopen_attempts;
            else ++manual_resume.quick_attempts;
            if(!output.started ||
               !vh_audio_page_lease_ready(&output.lease)) {
                ++manual_resume.unsafe_requests;
                result=20;
                break;
            }
            const VhNativeSeq before_seq=seq;
            const VhAudioResample before_resampler=resampler;
            memcpy(&manual_spu_snapshot,&synth,sizeof synth);
            const VhAudioOutputRecovery before_recovery=recovery;
            const uint64_t before_pcm=pcm_page_fingerprint(
                                                out_48000,count);
            const uint64_t before_pages=recovery.pages_submitted;
            const uint64_t before_frames=recovery.frames_submitted;
            const uint64_t before_calls=output.timing.calls;
            /* Neither stop nor reopening may synthesize or re-submit
             * a PCM page: the already returned page stays immutable. */
            if(native_stop(&output) ||
               vh_audio_output_resume_recover(&ops,&recovery,reopen)) {
                ++manual_resume.unsafe_requests;
                result=21;
                break;
            }
            if(!output.started ||
               !vh_audio_page_lease_ready(&output.lease) ||
               memcmp(&seq,&before_seq,sizeof seq) ||
               memcmp(&resampler,&before_resampler,sizeof resampler) ||
               memcmp(&synth,&manual_spu_snapshot,sizeof synth) ||
               pcm_page_fingerprint(out_48000,count)!=before_pcm ||
               recovery.pages_submitted!=before_pages ||
               recovery.frames_submitted!=before_frames ||
               output.timing.calls!=before_calls ||
               recovery.submit_failures!=before_recovery.submit_failures ||
               recovery.restart_attempts!=before_recovery.restart_attempts ||
               recovery.recoveries!=before_recovery.recoveries ||
               recovery.resume_failures!=before_recovery.resume_failures ||
               recovery.resume_restarts!=before_recovery.resume_restarts+
                                                (unsigned)reopen ||
               recovery.resume_recoveries!=before_recovery.resume_recoveries+
                                                (unsigned)reopen) {
                ++manual_resume.state_mismatches;
                result=22;
                break;
            }
            if(reopen) ++manual_resume.reopen_ok;
            else ++manual_resume.quick_ok;
        }
        /* Current HELD state prevents a B "normal" mark when A is
         * still down. Only a neutral sample can rearm the gate. */
        const unsigned ab=(held&HidNpadButton_A ? VH_AUDIO_MARK_A : 0u) |
                          (held&HidNpadButton_B ? VH_AUDIO_MARK_B : 0u);
        /* A tag and the accepted-button counters must commit
         * together; failed marker writes never advance input state.
         * This also rejects duplicate/missing logical-page samples. */
        if (vh_audio_listener_input_page(
                &mark_buttons,&listening_marks,ab)) {
            result=13;
            break;
        }
        if (played_blocks % 128u == 0u) {
            printf("Blocks=%u fixture_switches=%u notes=%llu cycles=%u\n",
                   played_blocks,completed_switches,
                   (unsigned long long)seq.note_ons,seq.cycles_completed);
            printf("Manual X stop/start=%u/%u Y reopen=%u/%u ignored=%u\n",
                   manual_resume.quick_ok,manual_resume.quick_attempts,
                   manual_resume.reopen_ok,manual_resume.reopen_attempts,
                   manual_resume.ignored_chords);
            if (tick_frequency) {
                const uint64_t avg_us=
                    vh_audio_output_ticks_to_us(
                        compute.total_ticks,tick_frequency)/
                    (compute.rendered_pages?compute.rendered_pages:1u);
                const uint64_t max_us=
                    vh_audio_output_ticks_to_us(
                        compute.max_ticks,tick_frequency);
                printf("DSP compute avg=%llu us peak=%llu us, over budget=%llu\n",
                       (unsigned long long)avg_us,
                       (unsigned long long)max_us,
                       (unsigned long long)compute.over_budget);
            }
            const uint64_t total_wait_us=
                vh_audio_output_ticks_to_us(
                    output.timing.total_ticks,tick_frequency);
            const uint64_t max_wait_us=
                vh_audio_output_ticks_to_us(
                    output.timing.max_ticks,tick_frequency);
            printf("audout waits avg=%llu us peak=%llu us, >page=%llu failures=%llu\n",
                   (unsigned long long)(output.timing.calls
                       ? total_wait_us/output.timing.calls : 0u),
                   (unsigned long long)max_wait_us,
                   (unsigned long long)output.timing.waits_longer_than_page,
                   (unsigned long long)output.timing.failed_submissions);
            const VhAudioPageWaitBucket *normal=&output.scene_waits.ordinary;
            const VhAudioPageWaitBucket *boundary=
                &output.scene_waits.first_after_switch;
            printf("steady pages=%llu avg=%llu us peak=%llu us slow=%llu retries=%llu\n",
                   (unsigned long long)normal->pages,
                   (unsigned long long)(normal->pages
                       ? vh_audio_output_ticks_to_us(normal->total_ticks,
                           tick_frequency)/normal->pages : 0u),
                   (unsigned long long)vh_audio_output_ticks_to_us(
                       normal->peak_page_ticks,tick_frequency),
                   (unsigned long long)normal->slow_pages,
                   (unsigned long long)normal->retried_pages);
            printf("boundary pages=%llu avg=%llu us peak=%llu us slow=%llu retries=%llu\n",
                   (unsigned long long)boundary->pages,
                   (unsigned long long)(boundary->pages
                       ? vh_audio_output_ticks_to_us(boundary->total_ticks,
                           tick_frequency)/boundary->pages : 0u),
                   (unsigned long long)vh_audio_output_ticks_to_us(
                       boundary->peak_page_ticks,tick_frequency),
                   (unsigned long long)boundary->slow_pages,
                   (unsigned long long)boundary->retried_pages);
            consoleUpdate(NULL);
        }
    }
    /* A failed audoutPlayBuffer may have left its 0x1000-byte
     * static output page in flight. Stop MUST succeed before
     * closing the service; otherwise keep the page allocated and
     * mark this run failed. No background audio worker is spawned.
     */
    if (vh_audio_output_stop_close(&ops)) {
        if (!result) result=7;
        printf("audout stop unconfirmed; close skipped\n");
    }
    /* Freeze the focus evidence before drawing immutable report pages. */
    appletUnhook(&focus_cookie);
    vh_audio_assets_close(&user_assets);
    /* Printed proof must never be inferred merely from a clean
     * applet exit: check page identity, fixture-switch cadence, raw
     * timing and logical-page accounting before claiming a full run.
     */
    const int run_evidence=vh_audio_output_verify_run(
        &output.scene_waits,&recovery,&output.timing,
        played_blocks,completed_switches,MAX_PROBE_BLOCKS,
        user_files ? 0u : SYNTHETIC_SCENE_BLOCKS,
        result==0 && played_blocks==MAX_PROBE_BLOCKS);
    const int compute_evidence=vh_audio_compute_verify(
        &compute,played_blocks,completed_switches) ||
        vh_audio_compute_wait_verify(&compute_wait,&compute,
            &output.scene_waits,played_blocks,completed_switches);
    const int tail_evidence=vh_audio_last_returned_page_verify(
        &seam_stats,&listening_marks,played_blocks);
    const int seam_evidence=vh_audio_output_verify_pcm_seams(
        &seam_stats,&output.scene_waits,played_blocks) ||
        tail_evidence;
    const uint64_t joint_dsp=
        compute_wait.ordinary.dsp_over+
        compute_wait.first_after_switch.dsp_over;
    const uint64_t joint2=
        compute_wait.ordinary.both_over_2x+
        compute_wait.first_after_switch.both_over_2x;
    const uint64_t joint4=
        compute_wait.ordinary.both_over_4x+
        compute_wait.first_after_switch.both_over_4x;
    const int listen_evidence=vh_audio_listening_verify(
        &listening_marks,played_blocks) ||
        vh_audio_listening_verify_dsp_totals(
            &listening_marks,joint_dsp,joint2,joint4);
    const int poll_evidence=vh_audio_input_poll_verify(
        &input_poll,played_blocks) ||
        vh_audio_mark_buttons_verify(
            &mark_buttons,played_blocks,listening_marks.manual_marks,
            listening_marks.control_marks);
    if ((run_evidence<0 || seam_evidence || listen_evidence ||
         poll_evidence || compute_evidence) && result==0) result=10;
    const int manual_evidence=vh_audio_manual_verify(&manual_resume);
    const uint64_t failed_logical_pages=
        output.scene_waits.ordinary.failed_pages+
        output.scene_waits.first_after_switch.failed_pages;
    const int focus_evidence=vh_audio_applet_verify(&focus_events) ||
        focus_events.returned_pages!=played_blocks ||
        focus_events.failed_logical_submissions!=failed_logical_pages;
    if (manual_evidence && result==0) result=23;
    if (output.transport_health.timing_fault && result==0) result=28;
    if ((focus_evidence || focus_record_errors) && result==0) result=24;
    const unsigned verdict=(focus_evidence || focus_record_errors ||
                            output.transport_health.timing_fault)
        ? VH_AUDIO_REPORT_INVALID
        : vh_audio_report_focus_evidence(
            &focus_events,&manual_resume,run_evidence,seam_evidence,
            listen_evidence,poll_evidence,compute_evidence);
    /* A fully accounted PCM run with an unresolved HOME/foreground
     * transition cannot be passed off as completed device recovery. */
    if(result==0 && verdict==VH_AUDIO_REPORT_INCOMPLETE)
        result=26;
    const VhAudioProbeReport report={
        .output=&output,.manual=&manual_resume,
        .focus=&focus_events,.focus_errors=focus_record_errors,
        .recovery=&recovery,.seams=&seam_stats,
        .marks=&listening_marks,.poll=&input_poll,
        .buttons=&mark_buttons,
        .compute=&compute,.compute_wait=&compute_wait,
        .compute_evidence=compute_evidence,
        .tick_frequency=tick_frequency,
        .played=played_blocks,.switched=completed_switches,
        .user_files=(unsigned)user_files,.result=result,
        .seam_evidence=seam_evidence,.tail_evidence=tail_evidence,
        .listen_evidence=listen_evidence,.poll_evidence=poll_evidence,
        .verdict=verdict
    };
    /* All source assets and audout handles are already released.
     * Redrawing these fixed reports cannot affect playback timing. */
    unsigned report_page=0u;
    vh_audio_show_report(&report,report_page);
    while (appletMainLoop()) {
        padUpdate(&pad);
        const uint64_t buttons=padGetButtonsDown(&pad);
        unsigned commands=0u;
        if (buttons&HidNpadButton_Left)
            commands|=VH_AUDIO_REPORT_PREV;
        if (buttons&HidNpadButton_Right)
            commands|=VH_AUDIO_REPORT_NEXT;
        if (buttons&HidNpadButton_Plus)
            commands|=VH_AUDIO_REPORT_QUIT;
        const unsigned previous_page=report_page;
        const int nav=vh_audio_report_navigate(&report_page,commands);
        if (nav==1) break;
        if (nav<0) {
            result=15;
            break;
        }
        if (report_page!=previous_page)
            vh_audio_show_report(&report,report_page);
        consoleUpdate(NULL);
        svcSleepThread(100000000ll);
    }
    consoleExit(NULL);
    return result;
}
