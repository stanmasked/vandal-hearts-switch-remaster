/* Verify that arbitrary 44.1 kHz input block boundaries do not change
 * the produced 48 kHz stereo PCM. Generated source, no game assets.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"

#define INPUT_FRAMES 4096u
#define OUTPUT_CAP 5000u

static int16_t input[INPUT_FRAMES*2u];
static int16_t a[OUTPUT_CAP*2u], b[OUTPUT_CAP*2u];
static int16_t chunk[VH_AUDIO_RESAMPLE_MAX_FRAMES*2u];

static size_t convert(int16_t *dest,int variable) {
    VhAudioResample state;
    vh_audio_resample_reset(&state);
    size_t offset=0,written=0;
    while(offset<INPUT_FRAMES) {
        size_t n=variable ? 1u+((offset*13u+29u)%511u) : 512u;
        if(n>INPUT_FRAMES-offset) n=INPUT_FRAMES-offset;
        size_t produced=vh_audio_resample_process(
            &state,input+2u*offset,n,chunk,VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(produced>0 && produced<=VH_AUDIO_RESAMPLE_MAX_FRAMES);
        assert(written+produced<=OUTPUT_CAP);
        memcpy(dest+2u*written,chunk,produced*2u*sizeof(int16_t));
        written+=produced;
        offset+=n;
    }
    assert(state.input_frames==INPUT_FRAMES);
    return written;
}

int main(void) {
    for(size_t i=0;i<INPUT_FRAMES;i++) {
        input[2u*i]=(int16_t)((i*157u)%26000u-13000);
        input[2u*i+1u]=(int16_t)((i*271u)%22000u-11000);
    }
    size_t na=convert(a,0),nb=convert(b,1);
    assert(na==nb);
    assert(memcmp(a,b,na*2u*sizeof(int16_t))==0);
    printf("Native resampler partition invariant: PASS %zu frames\n",na);
    return 0;
}
