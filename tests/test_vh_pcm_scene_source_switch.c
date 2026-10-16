/* Host regression: seamless PCM clock when a scene changes its source.
 * Does not assert real VAB bank ownership or simulate Switch audout.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

#define BLOCKS 64u
static int16_t input[512u*2u], standard[640u*2u], replay[640u*2u];
static VhAudioResample a,b;
static void generate(unsigned block) {
    for (unsigned i=0;i<512u;i++) {
        const uint32_t t=block*512u+i;
        const int32_t v=block<32u ? (int32_t)(t*47u%24000u)-12000
                                   : (int32_t)(t*107u%20000u)-10000;
        input[2u*i]=(int16_t)v;
        input[2u*i+1u]=(int16_t)-v;
    }
}
int main(void) {
    vh_audio_resample_reset(&a);
    vh_audio_resample_reset(&b);
    uint64_t total_a=0,total_b=0;
    for (unsigned block=0;block<BLOCKS;block++) {
        generate(block);
        size_t n=vh_audio_resample_process(&a,input,512u,standard,640u);
        assert(n>=555u && n<=559u);
        /* Alternate output capacity at scene transition; no lost clock. */
        size_t m=vh_audio_resample_process(&b,input,512u,replay,640u);
        assert(n==m && memcmp(standard,replay,n*4u)==0);
        total_a+=n;total_b+=m;
        if (block==31u || block==32u) {
            assert(a.input_frames==(uint64_t)(block+1u)*512u);
            assert(a.next_output_tick==b.next_output_tick);
        }
    }
    assert(total_a==total_b && a.input_frames==BLOCKS*512u);
    puts("synthetic scene-source switch PCM time continuity: PASS");
    return 0;
}
