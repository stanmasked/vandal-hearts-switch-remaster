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
/* Snapshot wet history outside the 32-kB stack of the offline utility. */
static VhSpuReverb switch_reverb_snapshot;
static int16_t source[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

typedef struct {
    uint64_t output_frames, input_frames, notes, note_offs, events;
    unsigned bank_index, blocks, sent_to_reverb;
    unsigned prior_bank_active_voices, prior_bank_release_voices;
    unsigned prior_bank_pcm_references, prior_bank_voices_cleared;
    unsigned reverb_history_preserved_on_switch;
    uint64_t note_requests, unresolved_notes, fallback_notes;
    uint64_t cross_program_fallback_notes, out_of_range_fallback_notes;
    uint64_t reverb_send_notes, zero_gain_notes;
    uint64_t saturated_note_requests;
    uint64_t notes_while_release_active, saturated_with_release_requests;
    uint64_t adsr_release_slot_retirements;
    unsigned peak_active_voices, peak_releasing_voices;
    unsigned peak_releasing_voices_before_render;
    unsigned first_saturated_note_block, first_release_overlap_block;
    unsigned first_release_retirement_block, last_release_retirement_block;
    unsigned first_note_block, last_note_block;
    unsigned first_note_off_block, first_cross_program_block;
    unsigned first_out_of_range_block;
    unsigned cycles_completed, first_cycle_block, last_cycle_block;
    unsigned observed_tempo_changes, first_tempo_change_block;
    unsigned last_tempo_change_block, final_tempo_us_per_quarter;
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
    VhNativeSpu *spu;
    uint64_t requests, resolved, unresolved, fallback, reverb_sends;
    uint64_t saturated_requests;
    uint64_t release_overlap_requests, saturated_release_requests;
    unsigned peak_voices, peak_releasing;
    uint64_t cross_program, out_of_range;
    uint64_t zero_gain;
} ResolverAudit;
static ResolverAudit resolver_audit;

static int resolve_with_audit(void *context, unsigned program, unsigned note,
                              unsigned velocity, unsigned volume, unsigned pan,
                              VhSeqTone *tone) {
    ResolverAudit *audit=(ResolverAudit *)context;
    ++audit->requests;
    /* Sample the SPU just before the sequencer allocates a voice.
     * All 20 active slots signal allocation pressure, not necessarily
     * a physically audible dropped note. Count only resolved requests.
     */
    unsigned active_voices=0u, releasing_voices=0u;
    for(unsigned voice=0;voice<VH_NATIVE_MUSIC_VOICES;voice++) {
        const VhNativeVoice *v=&audit->spu->voice[voice];
        active_voices+=(v->active!=0);
        releasing_voices+=(v->active && v->adsr.phase==VH_ADSR_RELEASE);
    }
    if (active_voices>audit->peak_voices)
        audit->peak_voices=active_voices;
    if (releasing_voices>audit->peak_releasing)
        audit->peak_releasing=releasing_voices;
    const int rc=vh_native_vab_resolve(audit->bank,program,note,velocity,
                                       volume,pan,tone);
    if (rc) {
        ++audit->unresolved;
        return rc;
    }
    ++audit->resolved;
    if (active_voices==VH_NATIVE_MUSIC_VOICES)
        ++audit->saturated_requests;
    if (releasing_voices) {
        ++audit->release_overlap_requests;
        if (active_voices==VH_NATIVE_MUSIC_VOICES)
            ++audit->saturated_release_requests;
    }
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
        SceneMetric *metric=&scene_metrics[i];
        metric->bank_index=bank_id;
        /* Observe borrowed previous-bank PCM and Release voices before
         * switching. Production switch_scene must discard them without
         * touching STUDIO_C history or the caller-owned resampler clock.
         */
        const uint64_t prior_input_frames=resampler.input_frames;
        const uint64_t prior_output_tick=resampler.next_output_tick;
        if (i) {
            for (unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++) {
                const VhNativeVoice *voice=&spu.voice[v];
                metric->prior_bank_active_voices+=(voice->active!=0);
                metric->prior_bank_release_voices+=
                    (voice->active && voice->adsr.phase==VH_ADSR_RELEASE);
                metric->prior_bank_pcm_references+=(voice->pcm!=NULL);
            }
            memcpy(&switch_reverb_snapshot,&spu.reverb,
                   sizeof(switch_reverb_snapshot));
        }
        memset(&resolver_audit,0,sizeof(resolver_audit));
        resolver_audit.bank=&asset->bank;
        resolver_audit.spu=&spu;
        if ((!i && vh_native_seq_init(
                &seq,asset->seq,asset->seq_size,&spu,
                resolve_with_audit,&resolver_audit,0)) ||
            (i && vh_native_seq_switch_scene(
                &seq,asset->seq,asset->seq_size,&spu,
                resolve_with_audit,&resolver_audit,0))) {
            fprintf(stderr,"Native SEQ scene initialization failed\n");
            goto error;
        }
        if (i) {
            metric->reverb_history_preserved_on_switch=
                (memcmp(&spu.reverb,&switch_reverb_snapshot,
                        sizeof(switch_reverb_snapshot))==0);
            metric->prior_bank_voices_cleared=1u;
            for (unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++) {
                const VhNativeVoice *voice=&spu.voice[v];
                if (voice->active || voice->pcm!=NULL ||
                    voice->adsr.phase!=VH_ADSR_OFF)
                    metric->prior_bank_voices_cleared=0u;
            }
            if (!metric->prior_bank_voices_cleared ||
                !metric->reverb_history_preserved_on_switch ||
                !spu.reverb_enabled || spu.reverb_depth!=0.5f ||
                spu.interpolation!=VH_SPU_GAUSSIAN ||
                spu.steal_index || spu.frames_rendered ||
                seq.note_ons || seq.note_offs ||
                seq.spu!=&spu || seq.context!=&resolver_audit ||
                seq.bytes!=asset->seq ||
                resampler.input_frames!=prior_input_frames ||
                resampler.next_output_tick!=prior_output_tick) {
                fprintf(stderr,"Music bank switch retained a voice or reset DSP clocks\n");
                goto error;
            }
        }
        if (metric->prior_bank_release_voices>
                metric->prior_bank_active_voices ||
            metric->prior_bank_active_voices>VH_NATIVE_MUSIC_VOICES ||
            metric->prior_bank_pcm_references>VH_NATIVE_MUSIC_VOICES) {
            fprintf(stderr,"Previous-bank voice accounting failed\n");
            goto error;
        }
        metric->blocks=blocks;
        const uint64_t start_output=frame_total;
        for(unsigned b=0;b<blocks;b++) {
            const uint64_t previous_notes=seq.note_ons;
            const uint64_t previous_offs=seq.note_offs;
            const uint32_t previous_cycles=seq.cycles_completed;
            const uint32_t previous_tempo=seq.tempo;
            const uint64_t previous_cross=resolver_audit.cross_program;
            const uint64_t previous_outside=resolver_audit.out_of_range;
            const uint64_t previous_saturated=resolver_audit.saturated_requests;
            const uint64_t previous_release=resolver_audit.release_overlap_requests;
            if (vh_native_seq_advance_block(&seq)<0) {
                fprintf(stderr,"SEQ playback error\n");
                goto error;
            }
            if (seq.cycles_completed>previous_cycles) {
                if (!metric->first_cycle_block) metric->first_cycle_block=b+1u;
                metric->last_cycle_block=b+1u;
            }
            if (seq.tempo!=previous_tempo) {
                ++metric->observed_tempo_changes;
                if (!metric->first_tempo_change_block)
                    metric->first_tempo_change_block=b+1u;
                metric->last_tempo_change_block=b+1u;
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
            if (resolver_audit.saturated_requests>previous_saturated &&
                !metric->first_saturated_note_block)
                metric->first_saturated_note_block=b+1u;
            if (resolver_audit.release_overlap_requests>previous_release &&
                !metric->first_release_overlap_block)
                metric->first_release_overlap_block=b+1u;
            /* Post-dispatch measurement complements the pre-allocator
             * snapshots inside the resolver (which can see a burst
             * of multiple note-ons in a single 512-frame block).
             */
            unsigned active_after=0u, releasing_after=0u;
            uint8_t release_at_render[VH_NATIVE_MUSIC_VOICES]={0};
            for (unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++) {
                const VhNativeVoice *voice=&spu.voice[v];
                active_after+=(voice->active!=0);
                release_at_render[v]=(uint8_t)(voice->active &&
                                               voice->adsr.phase==VH_ADSR_RELEASE);
                releasing_after+=release_at_render[v];
                if (voice->active && voice->reverb_send)
                    metric->sent_to_reverb=1u;
            }
            if (active_after>metric->peak_active_voices)
                metric->peak_active_voices=active_after;
            if (releasing_after>metric->peak_releasing_voices_before_render)
                metric->peak_releasing_voices_before_render=releasing_after;
            vh_native_spu_render(&spu,source,VH_AUDIO_BLOCK_FRAMES);
            /* Count slots whose Release phase ran to completion in the
             * renderer, not voices overwritten by a new Note On.
             * Each 512-frame block is a single observation interval.
             */
            for (unsigned v=0;v<VH_NATIVE_MUSIC_VOICES;v++) {
                if (release_at_render[v] && !spu.voice[v].active) {
                    ++metric->adsr_release_slot_retirements;
                    if (!metric->first_release_retirement_block)
                        metric->first_release_retirement_block=b+1u;
                    metric->last_release_retirement_block=b+1u;
                }
            }
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
        metric->cycles_completed=seq.cycles_completed;
        metric->final_tempo_us_per_quarter=seq.tempo;
        metric->events=seq.dispatched_events;
        metric->note_requests=resolver_audit.requests;
        metric->unresolved_notes=resolver_audit.unresolved;
        metric->fallback_notes=resolver_audit.fallback;
        metric->cross_program_fallback_notes=resolver_audit.cross_program;
        metric->out_of_range_fallback_notes=resolver_audit.out_of_range;
        metric->reverb_send_notes=resolver_audit.reverb_sends;
        metric->zero_gain_notes=resolver_audit.zero_gain;
        metric->saturated_note_requests=resolver_audit.saturated_requests;
        metric->notes_while_release_active=resolver_audit.release_overlap_requests;
        metric->saturated_with_release_requests=resolver_audit.saturated_release_requests;
        metric->peak_releasing_voices=resolver_audit.peak_releasing;
        if (resolver_audit.peak_voices>metric->peak_active_voices)
            metric->peak_active_voices=resolver_audit.peak_voices;
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
            metric->first_out_of_range_block>blocks ||
            metric->first_saturated_note_block>blocks ||
            metric->peak_active_voices>VH_NATIVE_MUSIC_VOICES ||
            metric->peak_releasing_voices>metric->peak_active_voices ||
            metric->peak_releasing_voices_before_render>
                metric->peak_active_voices ||
            metric->adsr_release_slot_retirements>
                (uint64_t)VH_NATIVE_MUSIC_VOICES*blocks ||
            (metric->adsr_release_slot_retirements==0u)!=
                (metric->first_release_retirement_block==0u) ||
            (metric->adsr_release_slot_retirements==0u)!=
                (metric->last_release_retirement_block==0u) ||
            metric->first_release_retirement_block>blocks ||
            metric->last_release_retirement_block>blocks ||
            metric->notes_while_release_active>metric->notes ||
            metric->saturated_with_release_requests>
                metric->saturated_note_requests ||
            metric->saturated_with_release_requests>
                metric->notes_while_release_active ||
            (metric->notes_while_release_active==0u)!=
                (metric->first_release_overlap_block==0u) ||
            metric->first_release_overlap_block>blocks ||
            (metric->saturated_note_requests==0u)!=
                (metric->first_saturated_note_block==0u) ||
            metric->saturated_note_requests>metric->notes ||
            metric->first_cycle_block>blocks ||
            metric->last_cycle_block>blocks ||
            metric->first_tempo_change_block>blocks ||
            metric->last_tempo_change_block>blocks ||
            (metric->cycles_completed==0u)!=(metric->first_cycle_block==0u) ||
            (metric->cycles_completed==0u)!=(metric->last_cycle_block==0u) ||
            (metric->observed_tempo_changes==0u)!=
                (metric->first_tempo_change_block==0u) ||
            (metric->observed_tempo_changes==0u)!=
                (metric->last_tempo_change_block==0u) ||
            metric->final_tempo_us_per_quarter==0u) {
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
               "\"prior_bank_active_voices\":%u,"
               "\"prior_bank_release_voices\":%u,"
               "\"prior_bank_pcm_references\":%u,"
               "\"prior_bank_voices_cleared\":%s,"
               "\"reverb_history_preserved_on_switch\":%s,"
               "\"saturated_note_requests\":%" PRIu64 ","
               "\"notes_while_release_active\":%" PRIu64 ","
               "\"saturated_with_release_requests\":%" PRIu64 ","
               "\"adsr_release_slot_retirements\":%" PRIu64 ","
               "\"peak_active_voices\":%u,"
               "\"peak_releasing_voices\":%u,"
               "\"peak_releasing_voices_before_render\":%u,"
               "\"first_saturated_note_block\":%u,"
               "\"first_release_overlap_block\":%u,"
               "\"first_release_retirement_block\":%u,"
               "\"last_release_retirement_block\":%u,"
               "\"first_note_block\":%u,"
               "\"last_note_block\":%u,"
               "\"first_note_off_block\":%u,"
               "\"first_cross_program_block\":%u,"
               "\"first_out_of_range_block\":%u,"
               "\"cycles_completed\":%u,"
               "\"first_cycle_block\":%u,"
               "\"last_cycle_block\":%u,"
               "\"observed_tempo_changes\":%u,"
               "\"first_tempo_change_block\":%u,"
               "\"last_tempo_change_block\":%u,"
               "\"final_tempo_us_per_quarter\":%u,"
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
               m->prior_bank_active_voices,m->prior_bank_release_voices,
               m->prior_bank_pcm_references,
               m->prior_bank_voices_cleared?"true":"false",
               m->reverb_history_preserved_on_switch?"true":"false",
               m->saturated_note_requests,
               m->notes_while_release_active,
               m->saturated_with_release_requests,
               m->adsr_release_slot_retirements,
               m->peak_active_voices,m->peak_releasing_voices,
               m->peak_releasing_voices_before_render,
               m->first_saturated_note_block,m->first_release_overlap_block,
               m->first_release_retirement_block,
               m->last_release_retirement_block,
               m->first_note_block,m->last_note_block,
               m->first_note_off_block,m->first_cross_program_block,
               m->first_out_of_range_block,
               m->cycles_completed,m->first_cycle_block,m->last_cycle_block,
               m->observed_tempo_changes,m->first_tempo_change_block,
               m->last_tempo_change_block,m->final_tempo_us_per_quarter,
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
