/* Exact 32768-source-frame cue boundary: probe production 44.1->48k
 * interpolation independently of SPU wet state. Generated data only. */
#include "vh_audio_resample.h"
#include "vh_audio_output_ramp.h"
#include "vh_audio_stream.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static int16_t constant[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t silence[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

static unsigned count_nonzero(const int16_t *p,size_t frames) {
    unsigned nonzero=0;
    for(size_t i=0;i<frames*2u;i++) nonzero+=(p[i]!=0);
    return nonzero;
}

int main(void) {
    for(size_t i=0;i<VH_AUDIO_BLOCK_FRAMES;i++) {
        constant[2*i]=10000;
        constant[2*i+1]=-10000;
    }
    for(unsigned repeat=0;repeat<2;repeat++) {
        VhAudioResample converter;
        VhAudioOutputRamp ramp;
        vh_audio_resample_reset(&converter);
        vh_audio_output_ramp_arm(&ramp);
        unsigned accumulated=0;
        for(unsigned block=0;block<64;block++) {
            const size_t n=vh_audio_resample_process(&converter,
                constant,VH_AUDIO_BLOCK_FRAMES,output,
                VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(n>0 && n<=VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(vh_audio_output_ramp_apply(&ramp,output,n)==0);
            accumulated+=(unsigned)n;
        }
        assert(accumulated>35520 && accumulated<35776);
        assert(converter.input_frames==64u*VH_AUDIO_BLOCK_FRAMES);
        assert(ramp.position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
        /* At THIS exact synthetic musical boundary the next output
         * tick interpolates prior 10000 into current zero at 10500/48000. */
        const size_t n=vh_audio_resample_process(&converter,
            silence,VH_AUDIO_BLOCK_FRAMES,output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(n>0 && n<=VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(vh_audio_output_ramp_apply(&ramp,output,n)==0);
        assert(output[0]==7812 && output[1]==-7812);
        assert(count_nonzero(output,n)==2u);
        for(unsigned next=0;next<47;next++) {
            const size_t m=vh_audio_resample_process(&converter,
                silence,VH_AUDIO_BLOCK_FRAMES,output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(m>0);
            assert(vh_audio_output_ramp_apply(&ramp,output,m)==0);
            assert(count_nonzero(output,m)==0u);
        }
    }
    /* Guard against overfitting to the 64-block phase. The production
     * stateful converter has different source fractions across cue
     * boundaries. Each case gets its own independent resampler/ramp. */
    const unsigned prefix_lengths[]={
        1u,2u,3u,7u,8u,15u,16u,31u,32u,63u,64u,65u,127u,128u
    };
    for(size_t c=0;c<sizeof prefix_lengths/sizeof prefix_lengths[0];c++) {
        VhAudioResample converter;
        VhAudioOutputRamp ramp;
        vh_audio_resample_reset(&converter);
        vh_audio_output_ramp_arm(&ramp);
        for(unsigned block=0;block<prefix_lengths[c];block++) {
            const size_t frames=vh_audio_resample_process(&converter,
                constant,VH_AUDIO_BLOCK_FRAMES,output,
                VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(frames>0);
            assert(vh_audio_output_ramp_apply(&ramp,output,frames)==0);
        }
        const size_t first_frames=vh_audio_resample_process(&converter,
            silence,VH_AUDIO_BLOCK_FRAMES,output,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(first_frames>0);
        assert(vh_audio_output_ramp_apply(&ramp,output,first_frames)==0);
        assert(count_nonzero(output,first_frames)==2u);
        assert(output[0]>0 && output[1]==-output[0]);
        for(unsigned tail=0;tail<5u;tail++) {
            const size_t frames=vh_audio_resample_process(&converter,
                silence,VH_AUDIO_BLOCK_FRAMES,output,
                VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(frames>0);
            assert(vh_audio_output_ramp_apply(&ramp,output,frames)==0);
            assert(count_nonzero(output,frames)==0u);
        }
    }
    /* A nonzero source sample is not a promise of nonzero output:
     * signed integer interpolation truncates sub-LSB transition
     * residues to zero. The decoder permits 0..2 on the first page. */
    for(size_t i=0;i<VH_AUDIO_BLOCK_FRAMES;i++) {
        constant[2*i]=1;
        constant[2*i+1]=-1;
    }
    {
        VhAudioResample converter;
        VhAudioOutputRamp ramp;
        vh_audio_resample_reset(&converter);
        vh_audio_output_ramp_arm(&ramp);
        for(unsigned block=0;block<64;block++) {
            const size_t frames=vh_audio_resample_process(&converter,
                constant,VH_AUDIO_BLOCK_FRAMES,output,
                VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(frames>0);
            assert(vh_audio_output_ramp_apply(&ramp,output,frames)==0);
        }
        const size_t first=vh_audio_resample_process(&converter,
            silence,VH_AUDIO_BLOCK_FRAMES,output,
            VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(first>0);
        assert(vh_audio_output_ramp_apply(&ramp,output,first)==0);
        assert(count_nonzero(output,first)==0u);
        for(unsigned next=0;next<5u;next++) {
            const size_t frames=vh_audio_resample_process(&converter,
                silence,VH_AUDIO_BLOCK_FRAMES,output,
                VH_AUDIO_RESAMPLE_MAX_FRAMES);
            assert(frames>0);
            assert(vh_audio_output_ramp_apply(&ramp,output,frames)==0);
            assert(count_nonzero(output,frames)==0u);
        }
    }
    puts("PASS: small-amplitude cue transient rounds to 0 signed PCM sample values");
    puts("PASS: 14 additional source-clock cue boundary phases stay within one stereo transient");
    puts("PASS: exact 64x512 cue-boundary has 2 transient signed samples, no later PCM; replay 2/2");
    return 0;
}
