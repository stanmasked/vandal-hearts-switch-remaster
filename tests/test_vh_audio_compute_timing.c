/* Portable compute-time stats / failed audout page regression. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_compute_timing.h"

int main(void) {
    VhAudioComputeTiming s={0};
    assert(vh_audio_compute_verify(&s,0u)==0);
    assert(vh_audio_compute_record(&s,100u,200u)==0);
    assert(vh_audio_compute_record(&s,200u,200u)==0);
    assert(vh_audio_compute_record(&s,201u,200u)==0);
    assert(s.rendered_pages==3u && s.over_budget==1u);
    assert(s.total_ticks==501u && s.max_ticks==201u);
    assert(vh_audio_compute_verify(&s,3u)==0);
    assert(vh_audio_compute_verify(&s,2u)==0); /* final page unreturned */
    assert(vh_audio_compute_verify(&s,1u)==-1); /* two missing pages */
    assert(vh_audio_compute_verify(&s,4u)==-1);
    const VhAudioComputeTiming before=s;
    assert(vh_audio_compute_record(&s,5u,0u)==-1);
    assert(memcmp(&s,&before,sizeof s)==0);
    assert(vh_audio_compute_record(NULL,3u,4u)==-1);

    VhAudioComputeTiming broken=s;
    broken.max_ticks=broken.total_ticks+1u;
    assert(vh_audio_compute_verify(&broken,3u)==-1);
    broken=s;
    broken.over_budget=broken.rendered_pages+1u;
    assert(vh_audio_compute_verify(&broken,3u)==-1);
    broken=(VhAudioComputeTiming){.total_ticks=1u};
    assert(vh_audio_compute_verify(&broken,0u)==-1);

    broken=s;
    broken.total_ticks=UINT64_MAX;
    assert(vh_audio_compute_record(&broken,1u,200u)==-1);
    assert(broken.rendered_pages==s.rendered_pages &&
           broken.total_ticks==UINT64_MAX);
    broken=s;
    broken.rendered_pages=UINT64_MAX;
    const VhAudioComputeTiming saturated=broken;
    assert(vh_audio_compute_record(&broken,1u,200u)==-1);
    assert(memcmp(&broken,&saturated,sizeof broken)==0);
    broken=s;
    broken.over_budget=UINT64_MAX;
    const VhAudioComputeTiming overflow=broken;
    assert(vh_audio_compute_record(&broken,201u,200u)==-1);
    assert(memcmp(&broken,&overflow,sizeof broken)==0);

    /* The first processed page is still counted if the output fails.
     * A fully completed run must have no outstanding synthesized page. */
    VhAudioComputeTiming interrupted={0};
    assert(vh_audio_compute_record(&interrupted,250u,200u)==0);
    assert(vh_audio_compute_verify(&interrupted,0u)==0);
    assert(vh_audio_compute_verify(&interrupted,1u)==0);
    puts("audout DSP compute budget and undelivered-page audit: PASS");
    return 0;
}
