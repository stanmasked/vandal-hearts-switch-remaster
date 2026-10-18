#include "vh_audio_playbuffer_history.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_unwrapped_and_wrapped_source(void) {
    VhPlayBufferHistory h={0};
    vh_playbuffer_history_reset(&h);
    assert(vh_playbuffer_history_record(NULL,100,110,1)==-1);
    assert(vh_playbuffer_history_record(&h,0,110,1)==-1);
    assert(vh_playbuffer_history_record(&h,120,110,1)==-1);
    assert(vh_playbuffer_history_record(&h,100,110,2)==-1);
    assert(h.total_attempts==0 && h.rejected_clock_pairs==2u);
    vh_playbuffer_history_reset(&h);
    for(unsigned i=1;i<=20;i++) {
        const uint64_t begin=1000u+50u*i;
        const uint64_t end=begin+20u+i;
        assert(vh_playbuffer_history_record(&h,begin,end,i!=8u)==1);
    }
    assert(h.total_attempts==20u);
    assert(h.previous_end_guest_ns==2020u+20u);
    assert(h.rejected_clock_pairs==0);
    assert(h.last[0].sequence==17u);
    assert(h.last[3].sequence==20u);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_playbuffer_history_write_csv(&h,f)==16);
    rewind(f);
    char line[160];
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,
        "total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n")==0);
    for(unsigned seq=5;seq<=20;seq++) {
        assert(fgets(line,sizeof line,f));
        unsigned long long total,n,b,e;
        unsigned returned;
        assert(sscanf(line,"%llu,%llu,%llu,%llu,%u",
                      &total,&n,&b,&e,&returned)==5);
        assert(total==20u && n==seq);
        assert(b==1000u+50u*seq);
        assert(e==b+20u+seq);
        assert(returned==(seq!=8u));
    }
    assert(fgetc(f)==EOF);
    assert(fclose(f)==0);
    assert(vh_playbuffer_history_record(&h,1500,1600,1)==-1);
    assert(h.rejected_clock_pairs==1);
    f=tmpfile();
    assert(f);
    assert(vh_playbuffer_history_write_csv(&h,f)==-1);
    assert(fclose(f)==0);
}
static void test_empty_never_invents_a_call(void) {
    VhPlayBufferHistory h={0};
    vh_playbuffer_history_reset(&h);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_playbuffer_history_write_csv(&h,f)==0);
    rewind(f);
    char line[160];
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,
        "total_attempts,sequence,begin_guest_ns,end_guest_ns,lease_returned\n")==0);
    assert(fgetc(f)==EOF);
    assert(fclose(f)==0);
    assert(vh_playbuffer_history_write_csv(NULL,stdout)==-1);
    assert(vh_playbuffer_history_write_csv(&h,NULL)==-1);
}
int main(void) {
    test_unwrapped_and_wrapped_source();
    test_empty_never_invents_a_call();
    puts("Stage322 original last16 PlayBuffer guest history passed");
    return 0;
}
