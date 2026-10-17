/* Portable DSP ordinary/cue-boundary accounting and failed page test. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_compute_timing.h"

int main(void) {
    VhAudioComputeTiming s={0};
    assert(vh_audio_compute_verify(&s,0u,0u)==0);
    assert(vh_audio_compute_record(&s,100u,200u,0u)==0);
    assert(vh_audio_compute_record(&s,200u,200u,0u)==0);
    assert(vh_audio_compute_record(&s,201u,200u,1u)==0);
    assert(s.rendered_pages==3u && s.over_budget==1u);
    assert(s.last_after_switch==1u);
    assert(s.total_ticks==501u && s.max_ticks==201u);
    assert(s.ordinary.rendered_pages==2u);
    assert(s.ordinary.total_ticks==300u);
    assert(s.ordinary.max_ticks==200u && !s.ordinary.over_budget);
    assert(s.first_after_switch.rendered_pages==1u);
    assert(s.first_after_switch.total_ticks==201u);
    assert(s.first_after_switch.max_ticks==201u);
    assert(s.first_after_switch.over_budget==1u);
    assert(vh_audio_compute_verify(&s,3u,1u)==0);
    /* Last synthetic boundary page rendered but never returned. */
    assert(vh_audio_compute_verify(&s,2u,0u)==0);
    /* Counters alone allow ordinary(undelivered) + boundary(delivered)
     * here. The final rendered category rules out that chronology. */
    assert(vh_audio_compute_verify(&s,2u,1u)==-1);
    assert(vh_audio_compute_verify(&s,3u,0u)==-1);
    assert(vh_audio_compute_verify(&s,1u,0u)==-1);
    assert(vh_audio_compute_verify(&s,4u,1u)==-1);
    assert(vh_audio_compute_verify(&s,2u,3u)==-1);

    const VhAudioComputeTiming before=s;
    assert(vh_audio_compute_record(&s,5u,0u,0u)==-1);
    assert(vh_audio_compute_record(&s,5u,200u,2u)==-1);
    assert(vh_audio_compute_record(NULL,3u,4u,0u)==-1);
    assert(!memcmp(&s,&before,sizeof s));

    VhAudioComputeTiming bad=s;
    bad.max_ticks=bad.total_ticks+1u;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; bad.over_budget=bad.rendered_pages+1u;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; bad.last_after_switch=2u;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; bad.last_after_switch=0u;
    assert(vh_audio_compute_verify(&bad,2u,0u)==-1);
    bad=s; ++bad.first_after_switch.rendered_pages;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; ++bad.ordinary.total_ticks;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; bad.ordinary.max_ticks=bad.ordinary.total_ticks+1u;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; ++bad.first_after_switch.over_budget;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=s; bad.first_after_switch.max_ticks=200u;
    assert(vh_audio_compute_verify(&bad,3u,1u)==-1);
    bad=(VhAudioComputeTiming){.total_ticks=1u};
    assert(vh_audio_compute_verify(&bad,0u,0u)==-1);

    bad=s; bad.total_ticks=UINT64_MAX;
    const VhAudioComputeTiming saturated_global=bad;
    assert(vh_audio_compute_record(&bad,1u,200u,0u)==-1);
    assert(!memcmp(&bad,&saturated_global,sizeof bad));
    bad=s; bad.ordinary.rendered_pages=UINT64_MAX;
    const VhAudioComputeTiming saturated_bucket=bad;
    assert(vh_audio_compute_record(&bad,1u,200u,0u)==-1);
    assert(!memcmp(&bad,&saturated_bucket,sizeof bad));
    bad=s; bad.first_after_switch.total_ticks=UINT64_MAX;
    const VhAudioComputeTiming saturated_boundary=bad;
    assert(vh_audio_compute_record(&bad,1u,200u,1u)==-1);
    assert(!memcmp(&bad,&saturated_boundary,sizeof bad));
    bad=s; bad.over_budget=UINT64_MAX;
    const VhAudioComputeTiming saturated_slow=bad;
    assert(vh_audio_compute_record(&bad,201u,200u,1u)==-1);
    assert(!memcmp(&bad,&saturated_slow,sizeof bad));

    VhAudioComputeTiming interrupted={0};
    assert(vh_audio_compute_record(&interrupted,250u,200u,1u)==0);
    assert(vh_audio_compute_verify(&interrupted,0u,0u)==0);
    assert(vh_audio_compute_verify(&interrupted,1u,1u)==0);
    assert(vh_audio_compute_verify(&interrupted,0u,1u)==-1);

    /* Ordinary last page unreturned is also valid; neither group
     * should invent a separate undelivered page. */
    VhAudioComputeTiming ordinary_failed={0};
    assert(vh_audio_compute_record(&ordinary_failed,210u,200u,0u)==0);
    assert(vh_audio_compute_verify(&ordinary_failed,0u,0u)==0);
    assert(vh_audio_compute_verify(&ordinary_failed,1u,0u)==0);
    assert(ordinary_failed.last_after_switch==0u);
    VhAudioComputeTiming no_pages={0};
    no_pages.last_after_switch=1u;
    assert(vh_audio_compute_verify(&no_pages,0u,0u)==-1);

    puts("audout DSP ordinary/switch compute budget split: PASS");
    return 0;
}
