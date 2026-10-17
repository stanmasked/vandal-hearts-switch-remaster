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



/* Full four-view commit (wait pages, PCM seams, DSP/wait, A/B ring).
 * Inject one failure in each producer AFTER the audio service has
 * released the logical page; no partial telemetry may survive. */
static void full_audit(const VhAudioSceneWaits *w,
                       const VhAudioPcmSeams *s,
                       const VhAudioComputeWaitJoin *j,
                       const VhAudioListeningMarks *m) {
    assert(vh_audio_output_verify_pcm_seams(
        s,w,m->returned_pages)==0);
    audit(j,m);
    assert(w->ordinary.pages+w->first_after_switch.pages ==
           m->returned_pages);
}
static void full_must_fail(VhAudioSceneWaits *w,VhAudioPcmSeams *s,
                           VhAudioComputeWaitJoin *j,
                           VhAudioListeningMarks *m,
                           const int16_t *pcm,size_t frames,
                           unsigned scene,
                           const VhAudioSubmitTiming *before,
                           const VhAudioSubmitTiming *after,
                           uint64_t hz,unsigned dsp) {
    const VhAudioSceneWaits ow=*w;
    const VhAudioPcmSeams os=*s;
    const VhAudioComputeWaitJoin oj=*j;
    const VhAudioListeningMarks om=*m;
    assert(vh_audio_returned_page_telemetry_record(
        w,s,j,m,pcm,frames,scene,before,after,hz,dsp)==-1);
    assert(!memcmp(w,&ow,sizeof *w));
    assert(!memcmp(s,&os,sizeof *s));
    assert(!memcmp(j,&oj,sizeof *j));
    assert(!memcmp(m,&om,sizeof *m));
}
static void full_transaction_test(void) {
    const uint64_t hz=19200000u;
    const size_t frames=2u;
    const int16_t pcm[4]={100,-100,200,-200};
    VhAudioSceneWaits w={0};
    VhAudioPcmSeams s={0};
    VhAudioComputeWaitJoin j={0};
    VhAudioListeningMarks m={0};
    const VhAudioSubmitTiming first_before={0};
    VhAudioSubmitTiming first_after={0};
    assert(vh_audio_output_record_submit_timing(
        &first_after,400u,hz,frames,1)==0);
    full_must_fail(&w,&s,&j,&m,pcm,frames,1u,
                   &first_before,&first_after,hz,0u);
    full_must_fail(&w,&s,&j,&m,pcm,frames,2u,
                   &first_before,&first_after,hz,0u);
    full_must_fail(&w,&s,&j,&m,NULL,frames,0u,
                   &first_before,&first_after,hz,0u);
    full_must_fail(&w,&s,&j,&m,pcm,0u,0u,
                   &first_before,&first_after,hz,0u);
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &first_before,&first_after,hz,2u);
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &first_before,&first_before,hz,0u);
    assert(vh_audio_returned_page_telemetry_record(
        &w,&s,&j,&m,pcm,frames,0u,
        &first_before,&first_after,hz,0u)==0);
    full_audit(&w,&s,&j,&m);
    assert(m.returned_pages==1u && s.delivered_pages==1u);
    assert(s.first_wait_band==0u && j.ordinary.returned==1u);

    const VhAudioSubmitTiming next_before=first_after;
    VhAudioSubmitTiming next_after=next_before;
    assert(vh_audio_output_record_submit_timing(
        &next_after,1200u,hz,frames,1)==0);
    /* A scene page after the initial ordinary page is valid. */
    assert(vh_audio_returned_page_telemetry_record(
        &w,&s,&j,&m,pcm,frames,1u,
        &next_before,&next_after,hz,1u)==0);
    full_audit(&w,&s,&j,&m);
    assert(s.delivered_pages==2u);
    assert(w.first_after_switch.pages==1u &&
           j.first_after_switch.wait_band_pages[1]==1u);

    const VhAudioSubmitTiming third_before=next_after;
    VhAudioSubmitTiming third_after=third_before;
    assert(vh_audio_output_record_submit_timing(
        &third_after,2300u,hz,frames,1)==0);
    /* Stage 1 failure: scene wait histogram saturated. */
    w.ordinary.pages=UINT64_MAX;
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &third_before,&third_after,hz,1u);
    w.ordinary.pages=1u;

    /* Stage 2 failure: candidate seam counter saturated. */
    s.ordinary.count[2]=UINT64_MAX;
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &third_before,&third_after,hz,1u);
    s.ordinary.count[2]=0u;

    /* Stage 3 failure: DSP/wait histogram saturated. */
    j.ordinary.wait_band_pages[2]=UINT64_MAX;
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &third_before,&third_after,hz,1u);
    j.ordinary.wait_band_pages[2]=0u;

    /* Stage 4 failure: bad DSP flag in 32-page A/B lookback. */
    m.recent[1].dsp_over_budget=2u;
    full_must_fail(&w,&s,&j,&m,pcm,frames,0u,
                   &third_before,&third_after,hz,1u);
    m.recent[1].dsp_over_budget=1u;
    full_audit(&w,&s,&j,&m);

    /* All failures were nonmutating; same page still succeeds. */
    assert(vh_audio_returned_page_telemetry_record(
        &w,&s,&j,&m,pcm,frames,0u,
        &third_before,&third_after,hz,1u)==0);
    full_audit(&w,&s,&j,&m);
    assert(w.ordinary.pages==2u && m.returned_pages==3u &&
           s.delivered_pages==3u && j.ordinary.returned==2u);
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
    full_transaction_test();
    puts("audout DSP/listening returned-page atomic transaction: PASS");
    return 0;
}
