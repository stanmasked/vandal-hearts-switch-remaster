/* Stage351: pure C11 source-only reason code, post-join CSV guard suite.
 * Does not run libnx services or claim to measure actual audio output.
 */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_exit_tail_reason_stage351.h"

static VhAudioDiagnostics snapshot(unsigned abandoned) {
    VhAudioDiagnostics s={0};
    s.lease_pages_acquired=123;
    s.lease_pages_released=123u-abandoned;
    s.abandoned_sessions=abandoned;
    s.pages_submitted=122u;
    return s;
}

static void output_matches(VhAudioExitTailReason *w,
                           VhAudioExitOutputWitness *old,
                           VhAudioDiagnostics *s, unsigned code,
                           unsigned attempted, unsigned returned,
                           unsigned lease_acquired) {
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_tail_reason_write_csv(w,old,s,f)==8);
    rewind(f);
    char row[100];
    const char *const fixed[]={
        "scope,value\n","software_exit_tail_reason_only,1\n"
    };
    for (unsigned i=0;i<2u;i++) {
        assert(fgets(row,sizeof row,f));
        assert(!strcmp(row,fixed[i]));
    }
    assert(fgets(row,sizeof row,f));
    unsigned n=999;
    assert(sscanf(row,"tail_reason_code,%u",&n)==1 && n==code);
    assert(fgets(row,sizeof row,f));
    assert(sscanf(row,"tail_attempted,%u",&n)==1 && n==attempted);
    assert(fgets(row,sizeof row,f));
    assert(sscanf(row,"tail_descriptor_return_confirmed,%u",&n)==1
           && n==returned);
    assert(fgets(row,sizeof row,f));
    assert(sscanf(row,"tail_lease_acquired,%u",&n)==1
           && n==lease_acquired);
    assert(fgets(row,sizeof row,f));
    assert(!strcmp(row,"lease_pages_acquired,123\n"));
    assert(fgets(row,sizeof row,f));
    const char *release=s->lease_pages_released==123u
        ? "lease_pages_released,123\n" :
          "lease_pages_released,122\n";
    assert(!strcmp(row,release));
    assert(fgets(row,sizeof row,f));
    const char *abandoned=s->abandoned_sessions
        ? "abandoned_sessions,1\n":"abandoned_sessions,0\n";
    assert(!strcmp(row,abandoned));
    assert(fgetc(f)==EOF && !ferror(f));
    fclose(f);
}

static void test_success_and_never_attempted(void) {
    VhAudioExitTailReason reason={0};
    VhAudioExitOutputWitness tail={0};
    vh_audio_tail_reason_reset(&reason);
    vh_audio_exit_output_reset(&tail);
    VhAudioDiagnostics s=snapshot(0);
    output_matches(&reason,&tail,&s,0,0,0,0);
    vh_audio_tail_reason_record(&reason,VH_TAIL_RETURN_CONFIRMED);
    assert(vh_audio_exit_output_tail(&tail,120,130,1)==1);
    output_matches(&reason,&tail,&s,7,1,1,1);
}

static void test_all_failure_codes(void) {
    for(unsigned code=VH_TAIL_PRECONDITION_FAILED;
        code<=VH_TAIL_RELEASE_MISMATCH;code++) {
        VhAudioExitTailReason reason={0};
        VhAudioExitOutputWitness tail={0};
        VhAudioDiagnostics s=snapshot(code>=VH_TAIL_APPEND_FAILED);
        vh_audio_tail_reason_reset(&reason);
        vh_audio_exit_output_reset(&tail);
        vh_audio_tail_reason_record(&reason,(VhAudioTailReasonCode)code);
        assert(vh_audio_exit_output_tail(&tail,120,130,0)==1);
        output_matches(&reason,&tail,&s,code,1,0,
                       code>=VH_TAIL_APPEND_FAILED);
    }
}
static void test_rejected_inconsistent_software_reports(void) {
    VhAudioExitTailReason reason={0};
    VhAudioExitOutputWitness tail={0};
    vh_audio_tail_reason_reset(&reason);
    vh_audio_exit_output_reset(&tail);
    VhAudioDiagnostics s=snapshot(1);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,NULL)==-1);
    assert(vh_audio_tail_reason_write_csv(NULL,&tail,&s,f)==-1);
    assert(vh_audio_tail_reason_write_csv(&reason,NULL,&s,f)==-1);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,NULL,f)==-1);
    vh_audio_tail_reason_record(&reason,VH_TAIL_WAIT_FAILED);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    assert(vh_audio_exit_output_tail(&tail,120,130,0)==1);
    s=snapshot(0);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    s=snapshot(1);
    s.lease_pages_released=123;
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    s=snapshot(1);s.pages_submitted=123;
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    s=snapshot(1);s.lease_pages_acquired=UINT64_MAX;
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    s=snapshot(1);
    vh_audio_tail_reason_record(&reason,(VhAudioTailReasonCode)8);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    vh_audio_tail_reason_record(&reason,VH_TAIL_RETURN_CONFIRMED);
    assert(vh_audio_tail_reason_write_csv(&reason,&tail,&s,f)==-1);
    fclose(f);
}

int main(void) {
    test_success_and_never_attempted();
    test_all_failure_codes();
    test_rejected_inconsistent_software_reports();
    puts("Stage351 exit tail reason: 8 codes, source-only lease guards PASS");
    return 0;
}
