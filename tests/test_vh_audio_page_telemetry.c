/* Host synthetic page telemetry transaction. Does not exercise
 * physical Switch audio, game banks or copyrighted samples.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_page_telemetry.h"

static void audit(const VhAudioComputeWaitJoin *j,
                  const VhAudioListeningMarks *m) {
    assert(vh_audio_listening_verify(m,m->returned_pages)==0);
    assert(vh_audio_listening_verify_dsp_totals(
        m,j->ordinary.dsp_over+j->first_after_switch.dsp_over,
        j->ordinary.both_over_2x+j->first_after_switch.both_over_2x,
        j->ordinary.both_over_4x+j->first_after_switch.both_over_4x)==0);
    assert(m->returned_pages==
           j->ordinary.returned+j->first_after_switch.returned);
}

static void must_fail_unchanged(VhAudioComputeWaitJoin *j,
    VhAudioListeningMarks *m, unsigned band,unsigned scene,
    unsigned retry,uint32_t seam,unsigned dsp) {
    const VhAudioComputeWaitJoin before_j=*j;
    const VhAudioListeningMarks before_m=*m;
    assert(vh_audio_page_telemetry_record(
        j,m,band,scene,retry,seam,dsp)==-1);
    assert(!memcmp(j,&before_j,sizeof *j));
    assert(!memcmp(m,&before_m,sizeof *m));
}

int main(void) {
    VhAudioComputeWaitJoin joint={0};
    VhAudioListeningMarks marks={0};
    audit(&joint,&marks);

    /* Illegal classifier input or absent accumulator: no mutation. */
    must_fail_unchanged(&joint,&marks,4u,0u,0u,0u,0u);
    must_fail_unchanged(&joint,&marks,0u,2u,0u,0u,0u);
    must_fail_unchanged(&joint,&marks,0u,0u,2u,0u,0u);
    must_fail_unchanged(&joint,&marks,0u,0u,0u,65536u,0u);
    must_fail_unchanged(&joint,&marks,0u,0u,0u,0u,2u);
    assert(vh_audio_page_telemetry_record(
        NULL,&marks,0u,0u,0u,0u,0u)==-1);
    assert(vh_audio_page_telemetry_record(
        &joint,NULL,0u,0u,0u,0u,0u)==-1);

    /* Realistic synthetic classification across many ring wraps:
     * one logical page -> one joint observation -> one ring slot.
     */
    for (unsigned i=0u;i<100u;i++) {
        const unsigned scene=(unsigned)(i%17u==0u);
        const unsigned band=i%VH_AUDIO_WAIT_BANDS;
        const unsigned retry=(unsigned)(i%29u==7u);
        const unsigned dsp=(unsigned)(i%7u==3u);
        const uint32_t seam=i==0u ? 0u : 100u+i;
        assert(vh_audio_page_telemetry_record(
            &joint,&marks,band,scene,retry,seam,dsp)==0);
        audit(&joint,&marks);
        assert(marks.returned_pages==(uint64_t)i+1u);
    }
    assert(marks.returned_pages==100u);
    assert(joint.ordinary.returned==94u);
    assert(joint.first_after_switch.returned==6u);

    /* Previously diverged exact DSP/page totals: reject, no new page. */
    ++marks.dsp_over_pages;
    must_fail_unchanged(&joint,&marks,2u,0u,0u,100u,1u);
    --marks.dsp_over_pages;
    ++joint.ordinary.returned;
    must_fail_unchanged(&joint,&marks,2u,0u,0u,100u,1u);
    --joint.ordinary.returned;

    /* A raw-ring invalid byte can reject a listening observation
     * AFTER the candidate DSP+wait counters were staged.
     */
    const unsigned idx=(unsigned)((marks.returned_pages-1u)%
                                  VH_LISTEN_RECENT_PAGES);
    marks.recent[idx].dsp_over_budget=2u;
    must_fail_unchanged(&joint,&marks,3u,0u,0u,160u,1u);
    marks.recent[idx].dsp_over_budget=0u; /* restore to valid bit */
    /* The actual original value at idx depends on the synthetic i. */
    marks.recent[idx].dsp_over_budget=(unsigned)(99u%7u==3u);
    audit(&joint,&marks);

    /* An overflow in the candidate joint histogram must leave the
     * listening ring unchanged even when it could record the page.
     */
    const uint64_t original_band=joint.ordinary.wait_band_pages[3];
    joint.ordinary.wait_band_pages[3]=UINT64_MAX;
    must_fail_unchanged(&joint,&marks,3u,0u,0u,160u,0u);
    joint.ordinary.wait_band_pages[3]=original_band;

    /* A saturated listening-window presence count must not publish
     * the candidate joint counters, even when the joint update fits.
     * Existing DSP events in recent pages ensure this increments.
     */
    const uint64_t window_count=marks.windows_near_dsp_over;
    marks.windows_near_dsp_over=UINT64_MAX;
    must_fail_unchanged(&joint,&marks,2u,0u,0u,160u,1u);
    marks.windows_near_dsp_over=window_count;
    audit(&joint,&marks);
    assert(vh_audio_page_telemetry_record(
        &joint,&marks,3u,0u,1u,210u,1u)==0);
    audit(&joint,&marks);
    assert(marks.returned_pages==101u);
    puts("audout DSP/listening returned-page atomic transaction: PASS");
    return 0;
}
