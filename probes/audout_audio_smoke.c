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
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#define LOCAL_AUDIO_DIR "sdmc:/switch/vandal-hearts-remake/audio"
#define MAX_PROBE_BLOCKS 1200u

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
    /* Only the matching returned descriptor makes this single
     * page safe for the next block or a bank transition. */
    if (R_FAILED(audoutPlayBuffer(&dev->page,&returned))) return -1;
    return vh_audio_output_page_returned(&dev->page,returned) ? 0 : -1;
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
    consoleUpdate(NULL);

    NativeOutput output={0};
    VhAudioOutputRecovery recovery={0};
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
    uint64_t compute_ticks_total = 0, compute_ticks_max = 0;
    unsigned compute_over_budget = 0;
    unsigned played_blocks = 0;
    int result = 0;
    while (appletMainLoop() && played_blocks < MAX_PROBE_BLOCKS) {
        const uint64_t tick_begin = armGetSystemTick();
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
        compute_ticks_total += elapsed_ticks;
        if (elapsed_ticks > compute_ticks_max) compute_ticks_max = elapsed_ticks;
        if (elapsed_ticks > block_budget_ticks) ++compute_over_budget;
        /* Retry the same fully rendered page after a bounded backend
         * restart. A failed output must not advance any music clock.
         */
        if (vh_audio_output_submit_recover(&ops,&recovery,
                                           out_48000,count)) {
            result = 7;
            break;
        }
        ++played_blocks;
        if (played_blocks % 128u == 0u) {
            printf("Blocks=%u notes=%llu cycles=%u\n", played_blocks,
                   (unsigned long long)seq.note_ons,seq.cycles_completed);
            if (tick_frequency) {
                const unsigned long long max_us =
                    (unsigned long long)(compute_ticks_max*1000000u /
                                         tick_frequency);
                const unsigned long long avg_us =
                    (unsigned long long)(compute_ticks_total*1000000u /
                                         (tick_frequency * played_blocks));
                printf("DSP compute avg=%llu us peak=%llu us, over budget=%u\n",
                       avg_us, max_us, compute_over_budget);
            }
            consoleUpdate(NULL);
        }
    }
    /* The blocking audoutPlayBuffer returned its buffer before we
     * release bank PCM. No audio thread may outlive this cleanup.
     */
    if (native_stop(&output)) result=7;
    native_close(&output);
    vh_audio_assets_close(&user_assets);
    printf("Output pages=%llu restarts=%u recovered=%u failures=%u\n",
           (unsigned long long)recovery.pages_submitted,
           recovery.restart_attempts,recovery.recoveries,
           recovery.submit_failures);
    printf("Audio probe ended, result=%d\n",result);
    consoleUpdate(NULL);
    consoleExit(NULL);
    return result;
}
