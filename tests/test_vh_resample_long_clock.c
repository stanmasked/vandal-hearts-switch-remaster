/* Long-run sample-clock regression: 44.1k -> 48k stereo PCM.
 * Only generated input; bounds integer phase error, including irregular chunks.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

#define BLOCKS 8192u
static VhAudioResample converter;
static int16_t source[VH_AUDIO_BLOCK_FRAMES*2u];
static int16_t output[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];
int main(void) {
    vh_audio_resample_reset(&converter);
    uint64_t total=0, frames=0, nonzero=0;
    for (unsigned b=0;b<BLOCKS;b++) {
        size_t n=1u+((b*173u+511u)%512u);
        for(size_t i=0;i<n;i++) {
            uint64_t t=frames+i;
            source[2u*i]=(int16_t)((t*131u)%24000u-12000);
            source[2u*i+1u]=(int16_t)((t*223u)%22000u-11000);
        }
        size_t generated=vh_audio_resample_process(
            &converter, source, n, output, VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(generated>0 && generated<=VH_AUDIO_RESAMPLE_MAX_FRAMES);
        for(size_t i=0;i<generated*2u;i++)
            nonzero+=(output[i]!=0);
        frames+=n;
        total+=generated;
        assert(converter.input_frames==frames);
        /* Streaming interpolation can defer the final source frame. */
        const uint64_t ideal=(frames-1u)*160u/147u+1u;
        assert(total<=ideal+1u);
        assert(total+2u>=ideal);
    }
    assert(frames>1000000u && nonzero>100000u);
    printf("48k PCM clock: PASS input=%llu output=%llu blocks=%u\n",
        (unsigned long long)frames,(unsigned long long)total,BLOCKS);
    return 0;
}
