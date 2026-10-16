/* Synthetic tests of interval coverage; no Switch hardware claims. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_input_poll.h"
int main(void) {
    VhAudioInputPoll s={0};
    assert(vh_audio_input_poll_verify(&s,0u)==0);
    assert(vh_audio_input_poll_record(NULL,1u,1u)==-1);
    assert(vh_audio_input_poll_record(&s,1u,0u)==-1);
    assert(vh_audio_input_poll_record(&s,100u,10u)==0);
    assert(s.samples==1u && !s.max_gap_ticks);
    assert(vh_audio_input_poll_record(&s,99u,10u)==-1);
    assert(s.samples==1u && s.last_tick==100u);
    assert(vh_audio_input_poll_record(&s,110u,10u)==0);
    assert(s.samples==2u && s.max_gap_ticks==10u);
    assert(!s.gaps_over_page);
    assert(vh_audio_input_poll_record(&s,140u,10u)==0);
    assert(s.gaps_over_page==1u && !s.gaps_over_4pages);
    assert(vh_audio_input_poll_record(&s,185u,10u)==0);
    assert(s.gaps_over_page==2u && s.gaps_over_4pages==1u);
    assert(s.max_gap_ticks==45u);
    assert(vh_audio_input_poll_verify(&s,4u)==0);
    assert(vh_audio_input_poll_verify(&s,5u)==-1);
    VhAudioInputPoll broken=s;
    broken.gaps_over_4pages=3u;
    assert(vh_audio_input_poll_verify(&broken,4u)==-1);
    broken=s; broken.gaps_over_page=4u;
    assert(vh_audio_input_poll_verify(&broken,4u)==-1);
    broken=s; broken.gaps_over_page=UINT64_MAX;
    const VhAudioInputPoll before=broken;
    assert(vh_audio_input_poll_record(&broken,200u,10u)==-1);
    assert(memcmp(&before,&broken,sizeof broken)==0);
    assert(vh_audio_input_poll_record(&s,UINT64_MAX,UINT64_MAX)==0);
    assert(s.gaps_over_page==2u && s.gaps_over_4pages==1u);
    assert(vh_audio_input_poll_verify(&s,5u)==0);
    s.samples=UINT64_MAX;
    const VhAudioInputPoll end=s;
    assert(vh_audio_input_poll_record(&s,UINT64_MAX,10u)==-1);
    assert(memcmp(&s,&end,sizeof s)==0);
    assert(vh_audio_input_poll_verify(NULL,0u)==-1);
    puts("audout controller poll intervals: PASS");
    return 0;
}
