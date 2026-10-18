/* Deterministic 4-ms audout resume de-click envelope.
 * All fixtures are synthetic PCM16; no original game resources.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_output_ramp.h"

static void test_constant_pcm_boundary(void) {
    VhAudioOutputRamp ramp={VH_AUDIO_OUTPUT_RAMP_FRAMES};
    int16_t pcm[256u*2u];
    for(unsigned i=0;i<256u;i++) {
        pcm[2u*i]=32767;
        pcm[2u*i+1u]=-32768;
    }
    vh_audio_output_ramp_arm(&ramp);
    assert(vh_audio_output_ramp_apply(&ramp,pcm,256u)==0);
    assert(ramp.position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
    assert(pcm[0]==0 && pcm[1]==0);
    assert(pcm[2u*191u]==32767 && pcm[2u*191u+1u]==-32768);
    assert(pcm[2u*192u]==32767 && pcm[2u*192u+1u]==-32768);
    assert(pcm[2u*255u]==32767 && pcm[2u*255u+1u]==-32768);
    int prev_l=0,prev_r=0;
    for(unsigned i=0;i<192u;i++) {
        const int l=pcm[2u*i],r=pcm[2u*i+1u];
        assert(l>=prev_l && r<=prev_r);
        assert(l-prev_l>=0 && l-prev_l<=172);
        assert(prev_r-r>=0 && prev_r-r<=172);
        prev_l=l;prev_r=r;
    }
    /* No repeat attenuation on subsequent fully prepared pages. */
    int16_t unchanged[]={700,-900,-32768,32767};
    const int16_t copy[]={700,-900,-32768,32767};
    assert(vh_audio_output_ramp_apply(&ramp,unchanged,2u)==0);
    assert(memcmp(unchanged,copy,sizeof unchanged)==0);
}

static void test_spanning_multiple_pcm_pages(void) {
    VhAudioOutputRamp ramp={VH_AUDIO_OUTPUT_RAMP_FRAMES};
    vh_audio_output_ramp_arm(&ramp);
    int16_t a[64u*2u],b[64u*2u],c[128u*2u];
    for(unsigned i=0;i<64u*2u;i++) {
        a[i]=8000;b[i]=8000;
    }
    for(unsigned i=0;i<128u*2u;i++)c[i]=8000;
    assert(!vh_audio_output_ramp_apply(&ramp,a,64u));
    assert(ramp.position==64u);
    assert(a[0]==0 && a[1]==0);
    assert(a[126u]==(int16_t)(8000*63/191));
    assert(!vh_audio_output_ramp_apply(&ramp,b,64u));
    assert(ramp.position==128u);
    assert(b[0]==(int16_t)(8000*64/191));
    assert(!vh_audio_output_ramp_apply(&ramp,c,128u));
    assert(ramp.position==192u);
    assert(c[0]==(int16_t)(8000*128/191));
    assert(c[2u*63u]==8000);
    assert(c[2u*64u]==8000);
    assert(c[2u*127u]==8000);
    /* A later genuine resume starts the next page at digital zero. */
    vh_audio_output_ramp_arm(&ramp);
    int16_t again[]={3000,-3000,4000,-4000};
    assert(!vh_audio_output_ramp_apply(&ramp,again,2u));
    assert(again[0]==0 && again[1]==0);
    assert(again[2]==4000/191 && again[3]==-4000/191);
    assert(ramp.position==2u);
}

static void test_validation_and_silence(void) {
    VhAudioOutputRamp ramp={VH_AUDIO_OUTPUT_RAMP_FRAMES};
    int16_t page[2048u*2u]={0};
    assert(vh_audio_output_ramp_apply(NULL,page,64u)==-1);
    assert(vh_audio_output_ramp_apply(&ramp,NULL,64u)==-1);
    assert(vh_audio_output_ramp_apply(&ramp,page,2049u)==-1);
    assert(ramp.position==VH_AUDIO_OUTPUT_RAMP_FRAMES);
    assert(vh_audio_output_ramp_apply(&ramp,NULL,0u)==0);
    vh_audio_output_ramp_arm(NULL);
    vh_audio_output_ramp_arm(&ramp);
    assert(!vh_audio_output_ramp_apply(&ramp,page,192u));
    assert(ramp.position==192u);
    for(unsigned i=0;i<192u*2u;i++)assert(page[i]==0);
    ramp.position=193u;
    assert(vh_audio_output_ramp_apply(&ramp,page,1u)==-1);
    assert(ramp.position==193u);
    /* Never touch a buffer if validation rejected it. */
    page[0]=1000;
    assert(vh_audio_output_ramp_apply(&ramp,page,1u)==-1);
    assert(page[0]==1000);
}

int main(void) {
    test_constant_pcm_boundary();
    test_spanning_multiple_pcm_pages();
    test_validation_and_silence();
    puts("48-kHz 4-ms stereo de-click ramp: zero start, full-gain edge, "
         "no second fade and monotone bounds PASS");
    return 0;
}
