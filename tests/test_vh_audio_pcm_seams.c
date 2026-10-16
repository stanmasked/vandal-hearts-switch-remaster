/* Copyright-free PCM seam vs audout wait regression; host only. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_output_recovery.h"

int main(void) {
    const uint64_t hz=19200000u;
    const size_t frames=2u; /* 800 ticks per PCM page at 48 kHz. */
    const int16_t pcm[5][4]={
        {100,-100,200,-200},
        {1000,1000,-1000,1000},
        {3000,-3000,-3000,3000},
        {300,400,300,400},
        {300,400,300,400}
    };
    const uint64_t ticks[5]={400u,4000u,2500u,200u,1200u};
    const int scene[5]={0,0,1,0,1};
    VhAudioSceneWaits groups={0};
    VhAudioPcmSeams seams={0};
    VhAudioSubmitTiming timing={0};
    for (unsigned i=0;i<5u;i++) {
        const VhAudioSubmitTiming before=timing;
        if (i==2u) {
            /* Retry the SAME scene PCM page after one rejected call. */
            assert(vh_audio_output_record_submit_timing(
                &timing,1100u,hz,frames,0)==0);
            assert(vh_audio_output_record_submit_timing(
                &timing,1400u,hz,frames,1)==0);
        } else {
            assert(vh_audio_output_record_submit_timing(
                &timing,ticks[i],hz,frames,1)==0);
        }
        assert(vh_audio_output_record_scene_page(
            &groups,&before,&timing,hz,frames,scene[i],1)==0);
        assert(vh_audio_output_record_pcm_seam(
            &seams,pcm[i],frames,scene[i],&before,&timing,hz)==0);
        assert(seams.delivered_pages==i+1u);
        assert(vh_audio_output_verify_pcm_seams(&seams,&groups,i+1u)==0);
    }
    assert(groups.ordinary.pages==3u);
    assert(groups.first_after_switch.pages==2u);
    assert(groups.first_after_switch.retried_pages==1u);
    assert(groups.ordinary.wait_le_page==2u);
    assert(groups.ordinary.wait_gt_4pages==1u);
    assert(groups.first_after_switch.wait_le_4pages==1u);
    assert(groups.first_after_switch.wait_le_2pages==1u);
    assert(seams.ordinary.count[0]==1u);
    assert(seams.ordinary.count[3]==1u);
    assert(seams.first_after_switch.count[2]==1u);
    assert(seams.first_after_switch.count[1]==1u);
    assert(seams.ordinary.peak_abs_step[0]==3300u);
    assert(seams.ordinary.peak_abs_step[3]==1200u);
    assert(seams.first_after_switch.peak_abs_step[2]==4000u);
    assert(seams.first_after_switch.peak_abs_step[1]==0u);

    VhAudioPcmSeams tampered=seams;
    tampered.ordinary.count[3]++;
    assert(vh_audio_output_verify_pcm_seams(&tampered,&groups,5u)==-1);
    tampered=seams;
    tampered.first_after_switch.peak_abs_step[0]=1u;
    assert(vh_audio_output_verify_pcm_seams(&tampered,&groups,5u)==-1);
    tampered=seams;
    tampered.ordinary.peak_abs_step[3]=65536u;
    assert(vh_audio_output_verify_pcm_seams(&tampered,&groups,5u)==-1);
    assert(vh_audio_output_verify_pcm_seams(&seams,&groups,4u)==-1);
    assert(vh_audio_output_verify_pcm_seams(NULL,&groups,5u)==-1);

    const VhAudioPcmSeams before_bad=seams;
    VhAudioSubmitTiming a=timing,b=timing;
    ++b.calls; ++b.total_ticks;
    assert(vh_audio_output_record_pcm_seam(
        &seams,pcm[0],frames,0,&a,&b,0u)==-1);
    assert(vh_audio_output_record_pcm_seam(
        &seams,pcm[0],0u,0,&a,&b,hz)==-1);
    assert(vh_audio_output_record_pcm_seam(
        &seams,pcm[0],frames,2,&a,&b,hz)==-1);
    assert(vh_audio_output_record_pcm_seam(
        &seams,pcm[0],frames,0,&a,&a,hz)==-1);
    ++b.failed_submissions; /* zero accepted backend calls */
    assert(vh_audio_output_record_pcm_seam(
        &seams,pcm[0],frames,0,&a,&b,hz)==-1);
    assert(memcmp(&before_bad,&seams,sizeof seams)==0);

    VhAudioPcmSeams fresh={0};
    VhAudioSubmitTiming empty={0}, first={0};
    assert(vh_audio_output_record_submit_timing(
        &first,400u,hz,frames,1)==0);
    assert(vh_audio_output_record_pcm_seam(
        &fresh,pcm[0],frames,1,&empty,&first,hz)==-1);
    assert(fresh.delivered_pages==0u);
    puts("audout / PCM seam correlation: generated five-page trace PASS");
    return 0;
}
