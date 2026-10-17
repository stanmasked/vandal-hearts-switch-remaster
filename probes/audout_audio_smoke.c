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
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#define LOCAL_AUDIO_DIR "sdmc:/switch/vandal-hearts-remake/audio"
#define MAX_PROBE_BLOCKS 1200u
#define SYNTHETIC_SCENE_BLOCKS 64u

static VhAudioAssets user_assets;
static VhNativeVab synthetic_bank;
static VhNativeSeq seq;
static VhNativeSpu synth;
static VhAudioResample resampler;

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
    int initialized;
    int started;
} NativeOutput;

static void native_close(void *opaque) {
    NativeOutput *dev=opaque;
    if (!dev->initialized) return;
    audoutExit();
    dev->initialized=0;
    dev->started=0;
}
static int native_open(void *opaque) {
    NativeOutput *dev=opaque;
    if (dev->initialized || R_FAILED(audoutInitialize())) return -1;
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
        R_FAILED(audoutStartAudioOut())) return -1;
    dev->started=1;
    return 0;
}
static int native_stop(void *opaque) {
    NativeOutput *dev=opaque;
    if (!dev->started) return 0;
    if (R_FAILED(audoutStopAudioOut())) return -1;
    dev->started=0;
    return 0;
}
static int native_submit(void *opaque,const int16_t *pcm,size_t frames) {
    NativeOutput *dev=opaque;
    if (!dev->initialized || !dev->started ||
        pcm!=out_48000 || frames==0 ||
        frames>VH_AUDIO_RESAMPLE_MAX_FRAMES) return -1;
    dev->page.data_size=frames*2u*sizeof(int16_t);
    AudioOutBuffer *returned=NULL;
    /* Measure actual blocking service time (one invocation, including
     * failed attempts), separately from the pre-render DSP budget. */
    const uint64_t before=armGetSystemTick();
    const Result rc=audoutPlayBuffer(&dev->page,&returned);
    const uint64_t elapsed=armGetSystemTick()-before;
    const int accepted=R_SUCCEEDED(rc) &&
        vh_audio_output_page_returned(&dev->page,returned);
    if (vh_audio_output_record_submit_timing(
            &dev->timing,elapsed,armGetSystemTickFreq(),frames,accepted))
        return -1;
    return accepted ? 0 : -1;
}

/* Each report screen is deliberately short enough for a single
 * photograph of the Nintendo Switch framebuffer console. Called
 * only after stopped audout and released SD music assets.
 */
typedef struct {
    const NativeOutput *output;
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
    int result, seam_evidence, listen_evidence, poll_evidence;
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
    printf("Vandal Hearts - native audout diagnostic\n");
    if (page==0u) {
        printf("REPORT 1/3: DEVICE / SERVICE\n\n");
        printf("Source: %s\n",r->user_files ? "user SD music" : "generated fixture");
        printf("Result=%d  PCM accounting=%s\n",r->result,
               r->verdict==VH_AUDIO_REPORT_FULL ? "FULL" :
               r->verdict==VH_AUDIO_REPORT_INCOMPLETE ? "INCOMPLETE" :
                                                       "INVALID");
        printf("Pages %u/%u, fixture switches=%u\n",
               r->played,MAX_PROBE_BLOCKS,r->switched);
        printf("Backend calls=%llu  failed=%llu\n",
               (unsigned long long)r->output->timing.calls,
               (unsigned long long)r->output->timing.failed_submissions);
        printf("Peak wait=%llu us; >page calls=%llu\n",
               (unsigned long long)vh_audio_output_ticks_to_us(
                   r->output->timing.max_ticks,hz),
               (unsigned long long)r->output->timing.waits_longer_than_page);
        printf("Restarts=%u recovered=%u\n",
               r->recovery->restart_attempts,r->recovery->recoveries);
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
        printf("REPORT 2/3: PCM SEAMS / COUNTS\n\n");
        printf("Seam audit=%s; pages=%llu\n",
               r->seam_evidence ? "INVALID" : "VALID",
               (unsigned long long)pcm->delivered_pages);
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
    } else {
        printf("REPORT 3/3: HUMAN A / NORMAL B / ALL\n\n");
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
    const VhAudioOutputOps ops={
        &output,native_submit,native_stop,native_close,native_open,native_start
    };
    if (native_open(&output) || native_start(&output)) {
        printf("audout initialization or format negotiation failed\n");
        (void)native_stop(&output);
        native_close(&output);
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 2;
    }

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
        if (vh_audio_output_record_scene_page(
                &output.scene_waits,&before_submit,&output.timing,
                tick_frequency,count,(int)switched_this_block,
                submit_result==0)) {
            result=9;
            break;
        }
        if (submit_result) {
            result=7;
            break;
        }
        /* Audit only successfully released logical pages, not
         * failed attempts or a freshly rendered, undelivered page. */
        if (vh_audio_output_record_pcm_seam(
                &seam_stats,out_48000,count,(int)switched_this_block,
                &before_submit,&output.timing,tick_frequency)) {
            result=11;
            break;
        }
        /* Correlation uses only delivered logical PCM pages;
         * unsuccessful retries do not create separate samples. */
        if (vh_audio_compute_wait_record(
                &compute_wait,switched_this_block,
                (unsigned)(elapsed_ticks>block_budget_ticks),
                seam_stats.last_wait_band)) {
            result=17;
            break;
        }
        const uint64_t calls_this_page=
            output.timing.calls-before_submit.calls;
        if (vh_audio_listening_observe(
                &listening_marks,seam_stats.last_wait_band,
                switched_this_block,(unsigned)(calls_this_page>1u),
                seam_stats.last_abs_step)) {
            result=12;
            break;
        }
        ++played_blocks;
        completed_switches+=switched_this_block;
        /* Read A-button rising edge only after audout has returned
         * its PCM descriptor; do not touch SEQ, SPU or resampler. */
        padUpdate(&pad);
        const uint64_t sample_tick=armGetSystemTick();
        const uint64_t page_ticks=
            (uint64_t)count*tick_frequency/VH_NATIVE_AUDOUT_RATE;
        if (vh_audio_input_poll_record(&input_poll,sample_tick,page_ticks)) {
            result=14;
            break;
        }
        /* Current HELD state prevents a B "normal" mark when A is
         * still down. Only a neutral sample can rearm the gate. */
        const uint64_t held=padGetButtons(&pad);
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
    /* The blocking audoutPlayBuffer returned its buffer before we
     * release bank PCM. No audio thread may outlive this cleanup.
     */
    if (native_stop(&output)) result=7;
    native_close(&output);
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
    const int seam_evidence=vh_audio_output_verify_pcm_seams(
        &seam_stats,&output.scene_waits,played_blocks);
    const int listen_evidence=vh_audio_listening_verify(
        &listening_marks,played_blocks);
    const int poll_evidence=vh_audio_input_poll_verify(
        &input_poll,played_blocks) ||
        vh_audio_mark_buttons_verify(
            &mark_buttons,played_blocks,listening_marks.manual_marks,
            listening_marks.control_marks);
    if ((run_evidence<0 || seam_evidence || listen_evidence ||
         poll_evidence || compute_evidence) && result==0) result=10;
    const unsigned verdict=vh_audio_report_evidence(
        run_evidence,seam_evidence,listen_evidence,poll_evidence,
        compute_evidence);
    const VhAudioProbeReport report={
        .output=&output,.recovery=&recovery,.seams=&seam_stats,
        .marks=&listening_marks,.poll=&input_poll,
        .buttons=&mark_buttons,
        .compute=&compute,.compute_wait=&compute_wait,
        .compute_evidence=compute_evidence,
        .tick_frequency=tick_frequency,
        .played=played_blocks,.switched=completed_switches,
        .user_files=(unsigned)user_files,.result=result,
        .seam_evidence=seam_evidence,
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
