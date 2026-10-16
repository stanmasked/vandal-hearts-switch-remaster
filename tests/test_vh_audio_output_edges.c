/* Host-only tests for normal-exit PCM taper and resume latency stats.
 * No libnx device, private Vandal Hearts music, or clock assumptions.
 */
#include <assert.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "vh_audio_output_edges.h"

static void test_two_millisecond_tail_and_sentinel(void) {
    int16_t page[(VH_AUDIO_STOP_TAIL_FRAMES+5u)*2u];
    for(size_t i=0;i<sizeof page/sizeof page[0];++i)
        page[i]=12345;
    assert(vh_audio_stop_tail_build(NULL,VH_AUDIO_STOP_TAIL_FRAMES,
                                    1000,-1000)==-1);
    assert(vh_audio_stop_tail_build(page,VH_AUDIO_STOP_TAIL_FRAMES-1u,
                                    1000,-1000)==-1);
    for(size_t i=0;i<sizeof page/sizeof page[0];++i)
        assert(page[i]==12345);
    assert(vh_audio_stop_tail_build(page,VH_AUDIO_STOP_TAIL_FRAMES,
                                    INT16_MAX,INT16_MIN)==0);
    assert(page[0]==INT16_MAX && page[1]==INT16_MIN);
    assert(page[(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u]==0);
    assert(page[(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u+1u]==0);
    for(unsigned i=1;i<VH_AUDIO_STOP_TAIL_FRAMES;i++) {
        const int32_t prev_l=page[2u*(i-1u)];
        const int32_t prev_r=page[2u*(i-1u)+1u];
        const int32_t curr_l=page[2u*i],curr_r=page[2u*i+1u];
        assert(curr_l<=prev_l && curr_l>=0);
        assert(curr_r>=prev_r && curr_r<=0);
        assert(prev_l-curr_l<=346 && curr_r-prev_r<=346);
    }
    /* The page descriptor may be larger than the final 96 frames;
     * generating a tail must not erase unrelated descriptor storage. */
    for(size_t i=VH_AUDIO_STOP_TAIL_FRAMES*2u;
        i<sizeof page/sizeof page[0];++i)
        assert(page[i]==12345);
    assert(vh_audio_stop_tail_build(page,VH_AUDIO_STOP_TAIL_FRAMES,
                                    0,0)==0);
    for(unsigned i=0;i<VH_AUDIO_STOP_TAIL_FRAMES*2u;++i)
        assert(page[i]==0);
}

static void test_polarity_preserved_and_no_music_time(void) {
    int16_t out[VH_AUDIO_STOP_TAIL_FRAMES*2u];
    for(unsigned v=0;v<128u;++v) {
        const int16_t left=(int16_t)((int)v*512-32768);
        const int16_t right=(int16_t)(32767-(int)v*512);
        assert(vh_audio_stop_tail_build(
            out,VH_AUDIO_STOP_TAIL_FRAMES,left,right)==0);
        assert(out[0]==left && out[1]==right);
        assert(out[(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u]==0);
        assert(out[(VH_AUDIO_STOP_TAIL_FRAMES-1u)*2u+1u]==0);
        const int32_t max_left=left<0 ? -(int32_t)left:left;
        const int32_t max_right=right<0 ? -(int32_t)right:right;
        for(unsigned i=0;i<VH_AUDIO_STOP_TAIL_FRAMES;i++) {
            const int32_t l=out[i*2u],r=out[i*2u+1u];
            assert((left>=0 ? l>=0:l<=0));
            assert((right>=0 ? r>=0:r<=0));
            assert((l<0?-l:l)<=max_left && (r<0?-r:r)<=max_right);
        }
    }
}

static void test_resume_metrics_and_saturation(void) {
    VhAudioResumeLatency s={0};
    vh_audio_resume_latency_record(NULL,1u);
    vh_audio_resume_latency_record(&s,0u);
    assert(s.count==1u && s.min_ns==0u && s.max_ns==0u);
    vh_audio_resume_latency_record(&s,UINT64_C(1000000));
    vh_audio_resume_latency_record(&s,UINT64_C(50000000));
    vh_audio_resume_latency_record(&s,UINT64_C(50000001));
    vh_audio_resume_latency_record(&s,UINT64_C(100000000));
    vh_audio_resume_latency_record(&s,UINT64_C(100000001));
    assert(s.count==6u && s.min_ns==0u);
    assert(s.max_ns==UINT64_C(100000001));
    assert(s.last_ns==UINT64_C(100000001));
    assert(s.over_50ms==3u && s.over_100ms==1u);
    assert(s.sum_ns==UINT64_C(301000002));
    s.sum_ns=UINT64_MAX-3u;
    s.count=UINT64_MAX;
    s.over_50ms=UINT64_MAX;
    s.over_100ms=UINT64_MAX;
    vh_audio_resume_latency_record(&s,UINT64_C(150000000));
    assert(s.sum_ns==UINT64_MAX && s.count==UINT64_MAX);
    assert(s.over_50ms==UINT64_MAX && s.over_100ms==UINT64_MAX);
    assert(s.max_ns==UINT64_C(150000000));
    assert(s.last_ns==UINT64_C(150000000));
}

int main(void) {
    test_two_millisecond_tail_and_sentinel();
    test_polarity_preserved_and_no_music_time();
    test_resume_metrics_and_saturation();
    puts("2-ms normal-stop PCM taper and bounded resume timing: PASS");
    return 0;
}
