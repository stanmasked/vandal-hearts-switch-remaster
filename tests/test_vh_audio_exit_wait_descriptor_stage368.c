/* Stage368 no-extra-service C11 fail-closed software witness tests. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "vh_audio_exit_wait_descriptor_stage368.h"

static void check(unsigned code,int called,uint32_t raw,uint32_t count,
                  const void *released,const void *submitted,int valid) {
    VhAudioExitWaitDescriptor368 w={0};
    VhAudioTailWaitResult357 old={0};
    VhAudioExitTailReason reason={0};
    vh_tail368_reset(&w);vh_tail357_reset(&old);
    vh_audio_tail_reason_reset(&reason);
    vh_audio_tail_reason_record(&reason,(VhAudioTailReasonCode)code);
    if(called) {
        assert(vh_tail368_record(&w,raw,count,released,submitted)==0);
        vh_tail357_record(&old,raw);
        assert(vh_tail368_record(&w,raw,count,released,submitted)==-1);
    }
    FILE *f=tmpfile();assert(f);
    const int got=vh_tail368_write_csv(&w,&old,&reason,f);
    assert(got==(valid?8:-1));
    if (valid) {
        rewind(f);
        char line[128];
        assert(fgets(line,sizeof line,f) &&
               !strcmp(line,"scope,value\n"));
        assert(fgets(line,sizeof line,f) &&
               !strcmp(line,"software_wait_descriptor_only,1\n"));
        unsigned rows=1;
        while (fgets(line,sizeof line,f)) rows++;
        assert(rows==8u && !ferror(f));
    }
    fclose(f);
}
static void test_valid_outcomes(void) {
    int mine=1,other=2;
    for(unsigned code=0;code<=3;code++)
        check(code,0,0,0,NULL,&mine,1);
    check(4,1,UINT32_C(0xEA01),0,NULL,&mine,1);
    check(4,1,UINT32_C(0xEA01),1,&mine,&mine,1);
    check(5,1,0,0,NULL,&mine,1);
    check(6,1,0,1,&other,&mine,1);
    check(6,1,0,1,NULL,&mine,1);
    check(7,1,0,1,&mine,&mine,1);
    check(7,1,0,UINT32_MAX,&mine,&mine,1);
}
static void test_invalid_outcomes(void) {
    int mine=1,other=2;
    check(4,0,0,0,NULL,&mine,0);
    check(4,1,0,0,NULL,&mine,0);
    check(5,1,0,1,NULL,&mine,0);
    check(6,1,0,0,NULL,&mine,0);
    check(7,1,0,0,&mine,&mine,0);
    check(7,1,0,1,&other,&mine,0);
    check(7,1,UINT32_C(0xEA01),1,&mine,&mine,0);
    check(3,1,0,1,&mine,&mine,0);
    check(8,1,0,1,&mine,&mine,0);
}
static void test_legacy_sources_must_agree(void) {
    int mine=1;
    VhAudioExitWaitDescriptor368 w={0};
    VhAudioTailWaitResult357 old={0};
    VhAudioExitTailReason reason={0};
    vh_audio_tail_reason_reset(&reason);
    vh_tail357_reset(&old);
    vh_audio_tail_reason_record(&reason,VH_TAIL_WAIT_FAILED);
    assert(!vh_tail368_record(&w,UINT32_C(0xEA01),0,NULL,&mine));
    FILE *f=tmpfile();assert(f);
    assert(vh_tail368_write_csv(&w,&old,&reason,f)==-1);
    vh_tail357_record(&old,0);
    assert(vh_tail368_write_csv(&w,&old,&reason,f)==-1);
    vh_tail357_record(&old,UINT32_C(0xEA01));
    assert(vh_tail368_write_csv(&w,&old,&reason,f)==8);
    fclose(f);
    w.returned_pointer_matches_submitted=1;
    f=tmpfile();assert(f);
    assert(vh_tail368_write_csv(&w,&old,&reason,f)==-1);
    fclose(f);
    vh_tail368_reset(&w);
    assert(vh_tail368_record(&w,0,0,NULL,NULL)==-1);
    assert(!w.observed);
}
int main(void) {
    test_valid_outcomes();
    test_invalid_outcomes();
    test_legacy_sources_must_agree();
    puts("Stage368: real-wait descriptor tuple software-only invariants PASS");
    return 0;
}
