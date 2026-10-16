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
    if (vh_native_spu_set_interpolation(&synth, VH_SPU_GAUSSIAN))
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

    Result rc = audoutInitialize();
    if (R_FAILED(rc)) {
        printf("audout init failed: 0x%08x\n", rc);
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 2;
    }
    if (audoutGetSampleRate() != VH_NATIVE_AUDOUT_RATE ||
        audoutGetChannelCount() != 2u ||
        audoutGetPcmFormat() != PcmFormat_Int16) {
        printf("Unsupported audout format/rate\n");
        audoutExit();
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 3;
    }
    rc = audoutStartAudioOut();
    if (R_FAILED(rc)) {
        printf("audout start failed: 0x%08x\n", rc);
        audoutExit();
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 4;
    }

    AudioOutBuffer desc = {0};
    desc.buffer = out_48000;
    desc.buffer_size = sizeof(out_48000);
    if (desc.buffer_size != 0x1000u) {
        audoutStopAudioOut();
        audoutExit();
        vh_audio_assets_close(&user_assets);
        consoleExit(NULL);
        return 8;
    }
    unsigned played_blocks = 0;
    int result = 0;
    while (appletMainLoop() && played_blocks < MAX_PROBE_BLOCKS) {
        if (vh_native_seq_advance_block(&seq) < 0) {
            result = 5;
            break;
        }
        vh_native_spu_render(&synth, in_44100, VH_AUDIO_BLOCK_FRAMES);
        const size_t count = vh_audio_resample_process(
            &resampler, in_44100, VH_AUDIO_BLOCK_FRAMES,
            out_48000, VH_AUDIO_RESAMPLE_MAX_FRAMES);
        if (!count || count * 2u * sizeof(int16_t) > desc.buffer_size) {
            result = 6;
            break;
        }
        desc.data_size = count * 2u * sizeof(int16_t);
        AudioOutBuffer *released = NULL;
        rc = audoutPlayBuffer(&desc, &released);
        if (R_FAILED(rc)) {
            result = 7;
            break;
        }
        ++played_blocks;
        if (played_blocks % 128u == 0u) {
            printf("Blocks=%u  notes=%llu  cycles=%u\n",played_blocks,
                   (unsigned long long)seq.note_ons,seq.cycles_completed);
            consoleUpdate(NULL);
        }
    }
    /* The blocking audoutPlayBuffer returned its buffer before we
     * release bank PCM. No audio thread may outlive this cleanup.
     */
    audoutStopAudioOut();
    audoutExit();
    vh_audio_assets_close(&user_assets);
    printf("Audio probe ended, result=%d\n",result);
    consoleUpdate(NULL);
    consoleExit(NULL);
    return result;
}
