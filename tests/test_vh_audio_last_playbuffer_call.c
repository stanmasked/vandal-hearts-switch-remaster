#include "vh_audio_last_playbuffer_call.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_reuse_one_existing_clock_pair(void) {
    VhAudioLastPlayBufferCall w={0};
    vh_audio_last_playbuffer_reset(&w);
    assert(vh_audio_last_playbuffer_record(NULL,100,200,1)==-1);
    assert(vh_audio_last_playbuffer_record(&w,0,200,1)==-1);
    assert(vh_audio_last_playbuffer_record(&w,200,100,1)==-1);
    assert(vh_audio_last_playbuffer_record(&w,100,200,2)==-1);
    assert(vh_audio_last_playbuffer_record(&w,100,150,0)==0);
    assert(vh_audio_last_playbuffer_record(&w,200,550,1)==1);
    assert(vh_audio_last_playbuffer_record(&w,600,620,0)==0);
    assert(vh_audio_last_playbuffer_record(&w,650,800,1)==1);
    assert(w.attempts==4 && w.successes==2 && w.failures==2);
    assert(w.last_success_attempt==4);
    assert(w.last_success_begin_guest_ns==650);
    assert(w.last_success_end_guest_ns==800);
    assert(w.nonmonotonic_rejected==2);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_last_playbuffer_write_csv(&w,f)==7);
    rewind(f);
    char line[120];
    const char *expected[]={
        "event,value\n","attempts,4\n","successes,2\n","failures,2\n",
        "last_success_attempt,4\n",
        "last_success_begin_guest_ns,650\n",
        "last_success_end_guest_ns,800\n",
        "nonmonotonic_rejected,2\n"
    };
    for(unsigned i=0;i<sizeof(expected)/sizeof(expected[0]);i++) {
        assert(fgets(line,sizeof line,f));
        assert(strcmp(line,expected[i])==0);
    }
    assert(fgetc(f)==EOF && fclose(f)==0);
}
static void test_invalid_clock_does_not_replace_success(void) {
    VhAudioLastPlayBufferCall w={0};
    vh_audio_last_playbuffer_reset(&w);
    assert(vh_audio_last_playbuffer_record(&w,100,400,1)==1);
    assert(vh_audio_last_playbuffer_record(&w,300,500,1)==-1);
    assert(w.last_success_begin_guest_ns==100);
    assert(w.last_success_end_guest_ns==400);
    assert(w.successes==1 && w.attempts==1);
    assert(w.nonmonotonic_rejected==1);
    assert(vh_audio_last_playbuffer_write_csv(NULL,stdout)==-1);
    assert(vh_audio_last_playbuffer_write_csv(&w,NULL)==-1);
    vh_audio_last_playbuffer_reset(&w);
    assert(w.successes==0 && w.nonmonotonic_rejected==0);
}
int main(void) {
    test_reuse_one_existing_clock_pair();
    test_invalid_clock_does_not_replace_success();
    puts("Stage320 last PlayBuffer begin/end witness C11 passed");
    return 0;
}
