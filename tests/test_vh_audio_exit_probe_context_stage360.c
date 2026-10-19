/* Stage360 original periodic PRE-SUBMIT queue probe is NOT exit queue depth.
 * Native C11 tests never touch a libnx audout service or original PCM.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_exit_probe_context_stage360.h"

static void check(const VhTailProbeContext360 *s,
                  VhAudioTailReasonCode code,int lines) {
    VhAudioExitTailReason r={0};
    vh_audio_tail_reason_reset(&r);
    vh_audio_tail_reason_record(&r,code);
    FILE *f=tmpfile();assert(f);
    assert(vh_tail360_write_csv(s,&r,f)==lines);
    if(lines>=0) {
        rewind(f);
        char line[128];
        assert(fgets(line,sizeof line,f) && !strcmp(line,"scope,value\n"));
        unsigned rows=0;
        while(fgets(line,sizeof line,f)) ++rows;
        assert(rows==13u && !ferror(f));
    }
    fclose(f);
}
static void test_success_snapshot(void) {
    VhTailProbeContext360 s={0};
    VhAudoutQueueTelemetry t={0};
    t.attempts=25;t.probe_count=2;
    t.probe[0]=(VhAudoutProbeSample){1,100,9,1};
    t.probe[1]=(VhAudoutProbeSample){17,170,2,1};
    assert(!vh_tail360_capture(&s,&t,250,254));
    assert(s.captured==1 && s.last_probe_available==1);
    assert(s.last_probe_attempt==17 && s.last_probe_queue_count==2);
    assert(s.last_probe_age_ns==80);
    assert(s.normal_submit_attempts==25);
    check(&s,VH_TAIL_RETURN_CONFIRMED,13);
    check(&s,VH_TAIL_WAIT_FAILED,13); /* probe data is reason-independent */
}
static void test_failed_query_must_not_fake_zero_queue(void) {
    VhTailProbeContext360 s={0};
    VhAudoutQueueTelemetry t={0};
    t.attempts=20;t.probe_count=1;
    t.probe[0]=(VhAudoutProbeSample){17,155,123,0};
    assert(!vh_tail360_capture(&s,&t,200,212));
    assert(s.last_probe_available && s.last_probe_queue_status==0);
    assert(s.last_probe_queue_count==0 && s.last_probe_age_ns==45);
    check(&s,VH_TAIL_WAIT_FAILED,13);
}
static void test_missing_and_stale_probes(void) {
    VhTailProbeContext360 s={0};
    VhAudoutQueueTelemetry t={0};
    t.attempts=4097;t.probe_dropped=12;
    assert(!vh_tail360_capture(&s,&t,100000,100002));
    assert(!s.last_probe_available && s.probe_dropped==12);
    check(&s,VH_TAIL_WAIT_FAILED,13);
    vh_tail360_reset(&s);
    t.probe_count=1;
    t.probe[0]=(VhAudoutProbeSample){9,17,1,1};
    assert(!vh_tail360_capture(&s,&t,100000,100001));
    assert(s.last_probe_age_ns==99983);
    check(&s,VH_TAIL_WAIT_EMPTY,13);
}
static void test_reject_unsafe_or_nonmonotonic(void) {
    VhTailProbeContext360 s={0};
    VhAudoutQueueTelemetry t={0};
    assert(vh_tail360_capture(&s,&t,200,100)==-1);
    assert(!s.captured);
    assert(!vh_tail360_capture(&s,&t,200,205));
    assert(vh_tail360_capture(&s,&t,300,350)==-1);
    check(&s,VH_TAIL_NOT_ATTEMPTED,-1);
}
static void test_no_tail_is_explicit(void) {
    VhTailProbeContext360 s={0};
    check(&s,VH_TAIL_NOT_ATTEMPTED,13);
    check(&s,VH_TAIL_WAIT_FAILED,-1);
}
static void test_does_not_assume_future_queue_sample(void) {
    VhTailProbeContext360 s={0};
    VhAudoutQueueTelemetry t={0};
    t.attempts=3;t.probe_count=1;
    t.probe[0]=(VhAudoutProbeSample){1,900,9,1};
    assert(!vh_tail360_capture(&s,&t,600,601));
    assert(!s.last_probe_available && s.last_probe_queue_count==0);
    check(&s,VH_TAIL_RETURN_CONFIRMED,13);
}
int main(void) {
    test_success_snapshot();
    test_failed_query_must_not_fake_zero_queue();
    test_missing_and_stale_probes();
    test_reject_unsafe_or_nonmonotonic();
    test_no_tail_is_explicit();
    test_does_not_assume_future_queue_sample();
    puts("Stage360 existing pre-submit queue probe age and bounded exit context PASS");
    return 0;
}
