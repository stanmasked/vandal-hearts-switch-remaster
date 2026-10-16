/* Local-only original-format SEQ/VH/VB transition audit.
 * Explicitly invoked by the owner: reads two directories containing
 * music.seq/music.vh/music.vb. Never writes PCM, copies assets, or
 * prints file paths and music contents. JSON contains measurements only.
 */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "vh_audio_assets.h"
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"
#include "vh_native_seq.h"
#include "vh_native_spu.h"

#define MAX_SCENES 32u
#define MAX_BLOCKS 4096u

/* Large VAB structures and reverb workspace must not be on the stack. */
static VhAudioAssets banks[2];
static VhNativeSpu spu;
static VhNativeSeq seq;
static VhAudioResample resampler;
static int16_t source[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

typedef struct {
    uint64_t output_frames, input_frames, notes, events;
    unsigned bank_index, blocks, sent_to_reverb;
    uint32_t spu_seam, audout_seam, resampler_fraction;
} SceneMetric;
static SceneMetric scene_metrics[MAX_SCENES];

static int parse_range(const char *value, unsigned lower,
                       unsigned upper, unsigned *result) {
    char *end=NULL;
    errno=0;
    unsigned long number=strtoul(value,&end,10);
    if (errno || end==value || *end || number<lower || number>upper)
        return -1;
    *result=(unsigned)number;
    return 0;
}
static uint32_t absolute_delta(int a,int b) {
    const int difference=a-b; /* PCM16 subtraction cannot overflow int32. */
    return (uint32_t)(difference<0 ? -difference : difference);
}
static uint32_t max2(uint32_t a,uint32_t b) {return a>b?a:b;}

int main(int argc,char **argv) {
    unsigned scenes=4u,blocks=16u;
    if (argc<3 || argc>5 ||
        (argc>=4 && parse_range(argv[3],2u,MAX_SCENES,&scenes)) ||
        (argc==5 && parse_range(argv[4],1u,MAX_BLOCKS,&blocks))) {
        fprintf(stderr,"usage: %s BANK_A_DIR BANK_B_DIR [scenes:2..32] [blocks:1..4096]\n",
                argc ? argv[0] : "vh_local_music_transition_probe");
        return 2;
    }
    if (vh_audio_assets_load(&banks[0],argv[1])!=VH_AUDIO_ASSET_OK ||
        vh_audio_assets_load(&banks[1],argv[2])!=VH_AUDIO_ASSET_OK) {
        fprintf(stderr,"Invalid, incomplete or oversized local SEQ/VH/VB set\n");
        vh_audio_assets_close(&banks[0]);
        vh_audio_assets_close(&banks[1]);
        return 3;
    }
    vh_native_spu_reset(&spu);
    vh_audio_resample_reset(&resampler);
    if (vh_native_spu_set_interpolation(&spu,VH_SPU_GAUSSIAN) ||
        vh_native_spu_set_reverb(&spu,1,0.5f)) {
        fprintf(stderr,"SPU initialization failed\n");
        goto error;
    }
    int16_t last_source[2]={0,0},last_output[2]={0,0};
    int have_last=0;
    uint64_t frame_total=0;
    for (unsigned i=0;i<scenes;i++) {
        const unsigned bank_id=i%2u;
        VhAudioAssets *asset=&banks[bank_id];
        if ((!i && vh_native_seq_init(
                &seq,asset->seq,asset->seq_size,&spu,
                vh_native_vab_resolve,&asset->bank,0)) ||
            (i && vh_native_seq_switch_scene(
                &seq,asset->seq,asset->seq_size,&spu,
                vh_native_vab_resolve,&asset->bank,0))) {
            fprintf(stderr,"Native SEQ scene initialization failed\n");
            goto error;
        }
        SceneMetric *metric=&scene_metrics[i];
        metric->bank_index=bank_id;
        metric->blocks=blocks;
        const uint64_t start_output=frame_total;
        for(unsigned b=0;b<blocks;b++) {
            if (vh_native_seq_advance_block(&seq)<0) {
                fprintf(stderr,"SEQ playback error\n");
                goto error;
            }
            for (unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++)
                if (spu.voice[v].active && spu.voice[v].reverb_send)
                    metric->sent_to_reverb=1u;
            vh_native_spu_render(&spu,source,VH_AUDIO_BLOCK_FRAMES);
            if (b==0u && i && have_last) {
                metric->spu_seam=max2(
                    absolute_delta(source[0],last_source[0]),
                    absolute_delta(source[1],last_source[1]));
                metric->resampler_fraction=(uint32_t)(
                    resampler.next_output_tick%VH_NATIVE_AUDOUT_RATE);
            }
            const size_t frames=vh_audio_resample_process(
                &resampler,source,VH_AUDIO_BLOCK_FRAMES,
                output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
            if (!frames || frames>VH_AUDIO_RESAMPLE_MAX_FRAMES) {
                fprintf(stderr,"PCM resampling failed\n");
                goto error;
            }
            if (b==0u && i && have_last) {
                metric->audout_seam=max2(
                    absolute_delta(output[0],last_output[0]),
                    absolute_delta(output[1],last_output[1]));
            }
            last_source[0]=source[2u*(VH_AUDIO_BLOCK_FRAMES-1u)];
            last_source[1]=source[2u*(VH_AUDIO_BLOCK_FRAMES-1u)+1u];
            last_output[0]=output[2u*(frames-1u)];
            last_output[1]=output[2u*(frames-1u)+1u];
            have_last=1;
            frame_total+=frames;
        }
        metric->input_frames=(uint64_t)blocks*VH_AUDIO_BLOCK_FRAMES;
        metric->output_frames=frame_total-start_output;
        metric->notes=seq.note_ons;
        metric->events=seq.dispatched_events;
        if(spu.frames_rendered!=metric->input_frames) {
            fprintf(stderr,"SPU frame accounting failed\n");
            goto error;
        }
    }
    if(resampler.input_frames!=(uint64_t)scenes*blocks*VH_AUDIO_BLOCK_FRAMES ||
       resampler.next_output_tick!=frame_total*VH_AUDIO_SAMPLE_RATE) {
        fprintf(stderr,"PCM clock continuity check failed\n");
        goto error;
    }

    /* Release all borrowed bank-owned pointers before unloading PCM.
     * No audio callback exists in this offline tool.
     */
    vh_native_seq_stop(&seq);
    vh_native_spu_clear_voices_keep_reverb(&spu);
    vh_audio_assets_close(&banks[0]);
    vh_audio_assets_close(&banks[1]);

    printf("{\"schema\":\"vh_local_music_transition_v1\","
           "\"provenance\":\"user-local\","
           "\"music_bytes_exported\":false,"
           "\"sample_rate_hz\":48000,"
           "\"scenes\":%u,\"blocks_per_scene\":%u,"
           "\"input_frames\":%" PRIu64 ","
           "\"output_frames\":%" PRIu64 ",\"measurements\":[",
           scenes,blocks,(uint64_t)scenes*blocks*VH_AUDIO_BLOCK_FRAMES,
           frame_total);
    for (unsigned i=0;i<scenes;i++) {
        const SceneMetric *m=&scene_metrics[i];
        printf("%s{\"scene\":%u,\"bank\":\"%c\","
               "\"events\":%" PRIu64 ",\"resolved_notes\":%" PRIu64 ","
               "\"reverb_send_seen\":%s,"
               "\"spu_boundary_delta_pcm16\":%u,"
               "\"audout_boundary_delta_pcm16\":%u,"
               "\"resampler_boundary_fraction\":%u,"
               "\"input_frames\":%" PRIu64 ","
               "\"output_frames\":%" PRIu64 "}",
               i?",":"",i,m->bank_index?'B':'A',
               m->events,m->notes,m->sent_to_reverb?"true":"false",
               m->spu_seam,m->audout_seam,m->resampler_fraction,
               m->input_frames,m->output_frames);
    }
    puts("],\"audible_audio_verified\":false,\"original_ps1_parity_verified\":false}");
    return 0;
error:
    vh_native_seq_stop(&seq);
    vh_native_spu_clear_voices_keep_reverb(&spu);
    vh_audio_assets_close(&banks[0]);
    vh_audio_assets_close(&banks[1]);
    return 4;
}
