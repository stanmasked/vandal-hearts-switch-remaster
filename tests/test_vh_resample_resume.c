/* Stateful PCM resampler resume: copying state at a block boundary must
 * reproduce identical future audio with no duplicate or skipped frames.
 * Synthetic input only; this does not simulate the Switch audout service.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

static int16_t input[512u*2u];
static int16_t before[640u*2u], resumed[640u*2u];

int main(void) {
    VhAudioResample live, saved, restored;
    vh_audio_resample_reset(&live);
    for (unsigned block=0; block<128u; ++block) {
        for (size_t i=0;i<512u;i++) {
            uint32_t pos=block*512u+(uint32_t)i;
            input[2u*i]=(int16_t)((pos*173u)%25000u-12500);
            input[2u*i+1u]=(int16_t)((pos*107u)%21000u-10500);
        }
        if (block==32u) { saved=live; restored=saved; }
        size_t n=vh_audio_resample_process(&live,input,512u,before,640u);
        assert(n>=555u && n<=559u);
        if (block>=32u) {
            size_t m=vh_audio_resample_process(&restored,input,512u,resumed,640u);
            assert(m==n);
            assert(memcmp(before,resumed,n*2u*sizeof(int16_t))==0);
            assert(restored.input_frames==live.input_frames);
            assert(restored.next_output_tick==live.next_output_tick);
            assert(restored.previous_left==live.previous_left);
            assert(restored.previous_right==live.previous_right);
            assert(restored.have_previous==live.have_previous);
        }
    }
    puts("resampler state snapshot/resume PCM: PASS");
    return 0;
}
