/* Deterministic 44.1-to-48 kHz PCM stereo streaming regression. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_resample.h"
#include "vh_audio_stream.h"

static int16_t input[1024 * 2u];
static int16_t a[1300 * 2u], b[1300 * 2u];
static VhAudioResample left, right;

static void test_dc_and_first_linear_frames(void) {
    vh_audio_resample_reset(&left);
    for (unsigned i=0;i<1024;i++) {
        input[2u*i]=9000;
        input[2u*i+1u]=-13000;
    }
    const size_t n0=vh_audio_resample_process(&left,input,512,a,650);
    const size_t n1=vh_audio_resample_process(&left,input+1024,512,a+2*n0,650);
    assert(n0>=555 && n0<=559);
    assert(n1>=555 && n1<=559);
    for(size_t i=0;i<n0+n1;i++) {
        assert(a[2*i]==9000);
        assert(a[2*i+1]==-13000);
    }
    assert(left.input_frames==1024);
    assert(left.have_previous==1);
}

static void test_chunk_invariance_and_stereo(void) {
    for(unsigned i=0;i<1024;i++) {
        input[2u*i]=(int16_t)((int)i*45-19000);
        input[2u*i+1u]=(int16_t)(15000-(int)i*27);
    }
    vh_audio_resample_reset(&left);
    vh_audio_resample_reset(&right);
    size_t n=0,m=0;
    n+=vh_audio_resample_process(&left,input,512,a,650);
    n+=vh_audio_resample_process(&left,input+2*512,512,a+2*n,650);
    m+=vh_audio_resample_process(&right,input,240,b,650);
    m+=vh_audio_resample_process(&right,input+2*240,272,b+2*m,650);
    m+=vh_audio_resample_process(&right,input+2*512,512,b+2*m,650);
    assert(n==m);
    assert(n>=1110 && n<=1116);
    assert(memcmp(a,b,n*2u*sizeof(int16_t))==0);
    assert(a[0]==input[0] && a[1]==input[1]);
    /* 1st upsampled frame is at source position 147/160. */
    assert(a[2] == (int16_t)(
        ((int64_t)input[0]*(160-147)+(int64_t)input[2]*147)/160));
    assert(a[3] == (int16_t)(
        ((int64_t)input[1]*(160-147)+(int64_t)input[3]*147)/160));
}

static void test_capacity_and_restart(void) {
    vh_audio_resample_reset(&left);
    VhAudioResample snapshot=left;
    assert(vh_audio_resample_process(&left,input,512,a,100)==0);
    assert(memcmp(&left,&snapshot,sizeof left)==0);
    assert(vh_audio_resample_process(NULL,input,512,a,650)==0);
    assert(vh_audio_resample_process(&left,NULL,512,a,650)==0);
    assert(vh_audio_resample_process(&left,input,0,a,650)==0);
    assert(vh_audio_resample_process(&left,input,513,a,650)==0);
    assert(vh_audio_resample_process(&left,input,512,NULL,650)==0);
    assert(memcmp(&left,&snapshot,sizeof left)==0);
    vh_audio_resample_reset(&left);
    assert(left.input_frames==0 && left.next_output_tick==0);
}

int main(void) {
    assert(VH_NATIVE_AUDOUT_RATE==48000u);
    assert(VH_AUDIO_SAMPLE_RATE==44100u);
    test_dc_and_first_linear_frames();
    test_chunk_invariance_and_stereo();
    test_capacity_and_restart();
    puts("44.1k -> 48k stateful stereo resampler: PASS");
    return 0;
}
