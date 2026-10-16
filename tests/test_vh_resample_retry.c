/* Stress output rejection and recovery after failure; generated PCM only. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

static int16_t input[512 * 2], clean[640 * 2], recovered[640 * 2];
int main(void) {
    VhAudioResample a,b;
    for (size_t i=0;i<512u*2u;i++)
        input[i]=(int16_t)((int)(i*53u)%30000-15000);
    vh_audio_resample_reset(&a);
    vh_audio_resample_reset(&b);
    for (unsigned block=0; block<256; ++block) {
        size_t valid=vh_audio_resample_process(&a,input,512,clean,640);
        assert(valid>=555u && valid<=559u);
        VhAudioResample snapshot=b;
        int16_t sentinel[2]={12345,-12345};
        size_t failed=vh_audio_resample_process(&b,input,512,sentinel,1);
        assert(failed==0);
        assert(memcmp(&snapshot,&b,sizeof b)==0);
        assert(sentinel[0]==12345 && sentinel[1]==-12345);
        size_t actual=vh_audio_resample_process(&b,input,512,recovered,640);
        assert(actual==valid);
        assert(memcmp(recovered,clean,actual*2u*sizeof(int16_t))==0);
    }
    assert(a.input_frames==256u*512u && b.input_frames==a.input_frames);
    puts("resampler repeated reject/retry with identical PCM: PASS");
    return 0;
}
