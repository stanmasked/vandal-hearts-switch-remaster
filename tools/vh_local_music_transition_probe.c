/* Local-only original-format SEQ/VH/VB transition audit.
 * Explicitly invoked by the owner: reads two directories containing
 * music.seq/music.vh/music.vb. Never writes PCM, copies assets, or
 * prints file paths and music contents. JSON contains measurements only.
 */
#include <errno.h>
#include <inttypes.h>
#include <math.h>
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
    uint64_t output_frames, input_frames, notes, note_offs, events;
    unsigned bank_index, blocks, sent_to_reverb;
    uint64_t note_requests, unresolved_notes, fallback_notes;
    uint64_t cross_program_fallback_notes, out_of_range_fallback_notes;
    uint64_t reverb_send_notes, zero_gain_notes;
    unsigned first_note_block, last_note_block;
    unsigned first_note_off_block, first_cross_program_block;
    unsigned first_out_of_range_block;
    uint64_t nonzero_samples, clipped_samples;
    int64_t channel_sum[2];
    uint64_t channel_squared_sum[2];
    uint32_t peak_pcm16;
    uint32_t spu_seam, audout_seam, resampler_fraction;
} SceneMetric;
static SceneMetric scene_metrics[MAX_SCENES];

/* Local audit counters around the unchanged production bank resolver.
 * A fallback is any note not matched within its requested program range.
 */
typedef struct {
    VhNativeVab *bank;
    uint64_t requests, resolved, unresolved, fallback, reverb_sends;
    uint64_t cross_program, out_of_range;
    uint64_t zero_gain;
} ResolverAudit;
static ResolverAudit resolver_audit;

static int resolve_with_audit(void *context, unsigned program, unsigned note,
                              unsigned velocity, unsigned volume, unsigned pan,
                              VhSeqTone *tone) {
    ResolverAudit *audit=(ResolverAudit *)context;
    ++audit->requests;
    const int rc=vh_native_vab_resolve(audit->bank,program,note,velocity,
                                       volume,pan,tone);
    if (rc) {
        ++audit->unresolved;
        return rc;
    }
    ++audit->resolved;
    const VhVabTone *selected=
        &audit->bank->tones[audit->bank->selected_program]
                            [audit->bank->selected_tone];
    if (audit->bank->selected_program!=program) {
        ++audit->fallback;
        ++audit->cross_program;
    } else if (note<selected->low || note>selected->high) {
        ++audit->fallback;
        ++audit->out_of_range;
    }
    if (tone->reverb_send)
        ++audit->reverb_sends;
    if (tone->gain_left==0.f && tone->gain_right==0.f)
        ++audit->zero_gain;
    return 0;
}


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
        memset(&resolver_audit,0,sizeof(resolver_audit));
        resolver_audit.bank=&asset->bank;
        if ((!i && vh_native_seq_init(
                &seq,asset->seq,asset->seq_size,&spu,
                resolve_with_audit,&resolver_audit,0)) ||
            (i && vh_native_seq_switch_scene(
                &seq,asset->seq,asset->seq_size,&spu,
                resolve_with_audit,&resolver_audit,0))) {
            fprintf(stderr,"Native SEQ scene initialization failed\n");
            goto error;
        }
        SceneMetric *metric=&scene_metrics[i];
        metric->bank_index=bank_id;
        metric->blocks=blocks;
        const uint64_t start_output=frame_total;
        for(unsigned b=0;b<blocks;b++) {
            const uint64_t previous_notes=seq.note_ons;
            const uint64_t previous_offs=seq.note_offs;
            const uint64_t previous_cross=resolver_audit.cross_program;
            const uint64_t previous_outside=resolver_audit.out_of_range;
            if (vh_native_seq_advance_block(&seq)<0) {
                fprintf(stderr,"SEQ playback error\n");
                goto error;
            }
            if (seq.note_ons>previous_notes) {
                if (!metric->first_note_block) metric->first_note_block=b+1u;
                metric->last_note_block=b+1u;
            }
            if (seq.note_offs>previous_offs && !metric->first_note_off_block)
                metric->first_note_off_block=b+1u;
            if (resolver_audit.cross_program>previous_cross &&
                !metric->first_cross_program_block)
                metric->first_cross_program_block=b+1u;
            if (resolver_audit.out_of_range>previous_outside &&
                !metric->first_out_of_range_block)
                metric->first_out_of_range_block=b+1u;
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
            /* Full scene-output statistics, after resampling. Successfully
             * resolved SEQ notes can still be silent due to zero gain.
             * Wet tails may also continue into a scene with zero notes.
             */
            for (size_t sample=0;sample<frames*2u;sample++) {
                const int16_t value=output[sample];
                const uint32_t absolute=absolute_delta((int)value,0);
                metric->peak_pcm16=max2(metric->peak_pcm16,absolute);
                metric->nonzero_samples+=(value!=0);
                metric->clipped_samples+=(value==INT16_MIN ||
                                          value==INT16_MAX);
                const unsigned channel=(unsigned)(sample%2u);
                metric->channel_sum[channel]+=(int64_t)value;
                metric->channel_squared_sum[channel]+=
                    (uint64_t)((int64_t)value*(int64_t)value);
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
        metric->note_offs=seq.note_offs;
        metric->events=seq.dispatched_events;
        metric->note_requests=resolver_audit.requests;
        metric->unresolved_notes=resolver_audit.unresolved;
        metric->fallback_notes=resolver_audit.fallback;
        metric->cross_program_fallback_notes=resolver_audit.cross_program;
        metric->out_of_range_fallback_notes=resolver_audit.out_of_range;
        metric->reverb_send_notes=resolver_audit.reverb_sends;
        metric->zero_gain_notes=resolver_audit.zero_gain;
        if (metric->nonzero_samples>metric->output_frames*2u ||
            metric->clipped_samples>metric->output_frames*2u ||
            (metric->peak_pcm16==0u)!=(metric->nonzero_samples==0u)) {
            fprintf(stderr,"PCM scene amplitude accounting failed\n");
            goto error;
        }
        if ((metric->notes==0u)!=(metric->first_note_block==0u) ||
            (metric->notes==0u)!=(metric->last_note_block==0u) ||
            (metric->note_offs==0u)!=(metric->first_note_off_block==0u) ||
            (metric->cross_program_fallback_notes==0u)!=
                (metric->first_cross_program_block==0u) ||
            (metric->out_of_range_fallback_notes==0u)!=
                (metric->first_out_of_range_block==0u) ||
            metric->first_note_block>blocks ||
            metric->last_note_block>blocks ||
            metric->first_note_off_block>blocks ||
            metric->first_cross_program_block>blocks ||
            metric->first_out_of_range_block>blocks) {
            fprintf(stderr,"SEQ block-timing accounting failed\n");
            goto error;
        }
        if(resolver_audit.resolved!=metric->notes ||
           resolver_audit.requests!=resolver_audit.resolved+
                                     resolver_audit.unresolved ||
           resolver_audit.fallback>resolver_audit.resolved ||
           resolver_audit.fallback!=resolver_audit.cross_program+
                                   resolver_audit.out_of_range ||
           resolver_audit.reverb_sends>resolver_audit.resolved ||
           resolver_audit.zero_gain>resolver_audit.resolved) {
            fprintf(stderr,"SEQ note-resolution accounting failed\n");
            goto error;
        }
        if(spu.frames_rendered!=metric->input_frames) {
            fprintf(stderr,"SPU frame accounting failed\n");
            goto error;
        }
    }
    const uint64_t total_input=(uint64_t)scenes*blocks*VH_AUDIO_BLOCK_FRAMES;
    /* The last source sample cannot be linearly interpolated with an
     * unavailable future sample. For every complete 44.1-kHz stream,
     * exactly floor((N-1)*48000/44100)+1 output frames are expected,
     * independently of how the source is split across scene blocks.
     */
    const uint64_t exact_output=(total_input-1u)*VH_NATIVE_AUDOUT_RATE/
                                 VH_AUDIO_SAMPLE_RATE+1u;
    if(resampler.input_frames!=total_input ||
       resampler.next_output_tick!=frame_total*VH_AUDIO_SAMPLE_RATE ||
       frame_total!=exact_output) {
        fprintf(stderr,"PCM clock continuity or frame count failed\n");
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
               "\"note_offs\":%" PRIu64 ","
               "\"note_requests\":%" PRIu64 ","
               "\"unresolved_notes\":%" PRIu64 ","
               "\"fallback_notes\":%" PRIu64 ","
               "\"cross_program_fallback_notes\":%" PRIu64 ","
               "\"out_of_range_fallback_notes\":%" PRIu64 ","
               "\"direct_match_notes\":%" PRIu64 ","
               "\"reverb_send_notes\":%" PRIu64 ","
               "\"zero_gain_notes\":%" PRIu64 ","
               "\"first_note_block\":%u,"
               "\"last_note_block\":%u,"
               "\"first_note_off_block\":%u,"
               "\"first_cross_program_block\":%u,"
               "\"first_out_of_range_block\":%u,"
               "\"reverb_send_seen\":%s,"
               "\"peak_pcm16\":%u,"
               "\"nonzero_samples\":%" PRIu64 ","
               "\"clipped_samples\":%" PRIu64 ","
               "\"mean_pcm16_left\":%.3f,"
               "\"mean_pcm16_right\":%.3f,"
               "\"rms_pcm16_left\":%.3f,"
               "\"rms_pcm16_right\":%.3f,"
               "\"silent_pcm\":%s,"
               "\"spu_boundary_delta_pcm16\":%u,"
               "\"audout_boundary_delta_pcm16\":%u,"
               "\"resampler_boundary_fraction\":%u,"
               "\"input_frames\":%" PRIu64 ","
               "\"output_frames\":%" PRIu64 "}",
               i?",":"",i,m->bank_index?'B':'A',
               m->events,m->notes,m->note_offs,m->note_requests,
               m->unresolved_notes,m->fallback_notes,
               m->cross_program_fallback_notes,
               m->out_of_range_fallback_notes,m->notes-m->fallback_notes,
               m->reverb_send_notes,m->zero_gain_notes,
               m->first_note_block,m->last_note_block,
               m->first_note_off_block,m->first_cross_program_block,
               m->first_out_of_range_block,
               m->sent_to_reverb?"true":"false",
               m->peak_pcm16,m->nonzero_samples,m->clipped_samples,
               (double)m->channel_sum[0]/(double)m->output_frames,
               (double)m->channel_sum[1]/(double)m->output_frames,
               sqrt((double)m->channel_squared_sum[0]/
                    (double)m->output_frames),
               sqrt((double)m->channel_squared_sum[1]/
                    (double)m->output_frames),
               m->nonzero_samples?"false":"true",
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
