/* Independent synthetic correlation of returned PCM page classes:
 * compute overbudget ∩ backend wait >2x or >4x. No music or hardware.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_compute_wait_join.h"

static void sample_wait(VhAudioSceneWaits *s,unsigned category,
                        unsigned band,unsigned returned) {
    VhAudioPageWaitBucket *w=category
        ? &s->first_after_switch : &s->ordinary;
    ++w->pages;
    if (band==0u) ++w->wait_le_page;
    else if (band==1u) ++w->wait_le_2pages;
    else if (band==2u) ++w->wait_le_4pages;
    else ++w->wait_gt_4pages;
    if (!returned) {
        ++w->failed_pages;
        ++w->failed_in_band[band];
    }
}
static void record(VhAudioComputeTiming *c,VhAudioSceneWaits *w,
                   VhAudioComputeWaitJoin *j,unsigned cat,
                   uint64_t ticks,unsigned band,unsigned delivered) {
    assert(vh_audio_compute_record(c,ticks,200u,cat)==0);
    sample_wait(w,cat,band,delivered);
    if (delivered) assert(vh_audio_compute_wait_record(
        j,cat,(unsigned)(ticks>200u),band)==0);
}
int main(void) {
    VhAudioComputeTiming c={0};
    VhAudioSceneWaits waits={0};
    VhAudioComputeWaitJoin j={0};
    assert(vh_audio_compute_wait_verify(&j,&c,&waits,0u,0u)==0);
    record(&c,&waits,&j,0u,220u,3u,1u); /* DSP+wait>4x */
    record(&c,&waits,&j,1u,225u,1u,1u); /* DSP only */
    record(&c,&waits,&j,0u,100u,3u,1u); /* wait>4x only */
    record(&c,&waits,&j,0u,250u,2u,1u); /* DSP+wait>2x */
    assert(vh_audio_compute_wait_verify(&j,&c,&waits,4u,1u)==0);
    assert(j.ordinary.returned==3u && j.ordinary.dsp_over==2u);
    assert(j.ordinary.wait_over_2x==3u &&
           j.ordinary.both_over_2x==2u);
    assert(j.ordinary.wait_over_4x==2u &&
           j.ordinary.both_over_4x==1u);
    assert(j.first_after_switch.returned==1u &&
           j.first_after_switch.dsp_over==1u &&
           j.first_after_switch.wait_over_2x==0u);
    assert(j.ordinary.wait_band_pages[0]==0u &&
           j.ordinary.wait_band_pages[1]==0u &&
           j.ordinary.wait_band_pages[2]==1u &&
           j.ordinary.wait_band_pages[3]==2u);
    assert(j.ordinary.dsp_over_in_band[0]==0u &&
           j.ordinary.dsp_over_in_band[1]==0u &&
           j.ordinary.dsp_over_in_band[2]==1u &&
           j.ordinary.dsp_over_in_band[3]==1u);
    assert(j.first_after_switch.wait_band_pages[1]==1u);
    assert(j.first_after_switch.dsp_over_in_band[1]==1u);
    record(&c,&waits,&j,1u,300u,3u,0u); /* terminal failure */
    assert(c.last_after_switch==1u && c.last_over_budget==1u);
    assert(vh_audio_compute_wait_verify(&j,&c,&waits,4u,1u)==0);
    assert(vh_audio_compute_wait_verify(&j,&c,&waits,5u,1u)==-1);

    VhAudioComputeWaitJoin broken=j;
    broken.ordinary.both_over_4x=
        broken.ordinary.both_over_2x+1u;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    /* The new independent per-band counters catch a mismatch
     * between a refined histogram and its threshold summary. */
    broken=j;
    ++broken.ordinary.both_over_4x;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    /* A coordinated alternative distribution is still arithmetically
     * feasible: totals alone cannot recover the original timeline.
     * Do not pretend this is independently disprovable. */
    broken=j;
    --broken.ordinary.dsp_over_in_band[2];
    ++broken.ordinary.dsp_over_in_band[3];
    ++broken.ordinary.both_over_4x;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==0);
    broken=j;
    --broken.ordinary.both_over_2x;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.ordinary.wait_over_2x;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.first_after_switch.dsp_over;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.ordinary.returned;
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.ordinary.wait_band_pages[2];
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.ordinary.dsp_over_in_band[2];
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);
    broken=j; ++broken.first_after_switch.wait_band_pages[1];
    assert(vh_audio_compute_wait_verify(&broken,&c,&waits,4u,1u)==-1);

    VhAudioSceneWaits corrupt=waits;
    ++corrupt.ordinary.wait_le_4pages;
    assert(vh_audio_compute_wait_verify(&j,&c,&corrupt,4u,1u)==-1);
    corrupt=waits; ++corrupt.first_after_switch.failed_in_band[3];
    assert(vh_audio_compute_wait_verify(&j,&c,&corrupt,4u,1u)==-1);
    corrupt=waits; corrupt.ordinary.failed_in_band[3]=UINT64_MAX;
    assert(vh_audio_compute_wait_verify(&j,&c,&corrupt,4u,1u)==-1);

    VhAudioComputeWaitJoin unchanged=j;
    assert(vh_audio_compute_wait_record(&j,2u,1u,3u)==-1);
    assert(vh_audio_compute_wait_record(&j,0u,2u,3u)==-1);
    assert(vh_audio_compute_wait_record(&j,0u,1u,4u)==-1);
    assert(!memcmp(&j,&unchanged,sizeof j));
    broken=j; broken.ordinary.returned=UINT64_MAX;
    unchanged=broken;
    assert(vh_audio_compute_wait_record(&broken,0u,1u,3u)==-1);
    assert(!memcmp(&broken,&unchanged,sizeof broken));
    broken=j; broken.ordinary.both_over_2x=UINT64_MAX;
    unchanged=broken;
    assert(vh_audio_compute_wait_record(&broken,0u,1u,3u)==-1);
    assert(!memcmp(&broken,&unchanged,sizeof broken));
    broken=j; broken.ordinary.wait_band_pages[3]=UINT64_MAX;
    unchanged=broken;
    assert(vh_audio_compute_wait_record(&broken,0u,0u,3u)==-1);
    assert(!memcmp(&broken,&unchanged,sizeof broken));
    broken=j; broken.ordinary.dsp_over_in_band[3]=UINT64_MAX;
    unchanged=broken;
    assert(vh_audio_compute_wait_record(&broken,0u,1u,3u)==-1);
    assert(!memcmp(&broken,&unchanged,sizeof broken));

    /* Another failure with ordinary page at <=1x and no DSP overrun:
     * subtraction must not remove a successful DSP overrun. */
    VhAudioComputeTiming alt={0};
    VhAudioSceneWaits aw={0};
    VhAudioComputeWaitJoin aj={0};
    record(&alt,&aw,&aj,0u,300u,3u,1u);
    record(&alt,&aw,&aj,0u,100u,0u,0u);
    assert(alt.last_over_budget==0u);
    assert(vh_audio_compute_wait_verify(&aj,&alt,&aw,1u,0u)==0);
    assert(aj.ordinary.wait_band_pages[3]==1u);
    assert(aj.ordinary.wait_band_pages[0]==0u);
    assert(aj.ordinary.dsp_over_in_band[3]==1u);

    /* Exercise every ordinary/switch wait range for a longer trace:
     * terminally failed pages must NOT enter returned-page bands. */
    VhAudioComputeTiming trace={0};
    VhAudioSceneWaits tw={0};
    VhAudioComputeWaitJoin tj={0};
    for (unsigned k=0u;k<256u;k++) {
        const unsigned cat=(k%19u==0u);
        const unsigned band=k%VH_AUDIO_WAIT_BANDS;
        const uint64_t ticks=(k%7u==0u)?210u:90u;
        record(&trace,&tw,&tj,cat,ticks,band,1u);
        assert(vh_audio_compute_wait_verify(
            &tj,&trace,&tw,k+1u,trace.first_after_switch.rendered_pages)==0);
    }
    for (unsigned band=0u;band<VH_AUDIO_WAIT_BANDS;band++) {
        assert(tj.ordinary.wait_band_pages[band]>0u);
        assert(tj.first_after_switch.wait_band_pages[band]>0u);
    }
    record(&trace,&tw,&tj,1u,211u,3u,0u);
    assert(vh_audio_compute_wait_verify(
        &tj,&trace,&tw,256u,trace.first_after_switch.rendered_pages-1u)==0);

    puts("DSP/audout same-page >2x/>4x correlation: PASS");
    return 0;
}
