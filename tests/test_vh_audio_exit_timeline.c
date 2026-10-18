#include "vh_audio_exit_timeline.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void expect_line(FILE *f,const char *expect) {
    char line[128];
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,expect)==0);
}

static void test_once_and_round_trip(void) {
    VhAudioExitTimeline timeline = {0};
    vh_audio_exit_timeline_reset(&timeline);
    for(unsigned i=0;i<VH_EXIT_EVENT_COUNT;i++)
        assert(vh_audio_exit_timeline_get(&timeline,i)==0);
    assert(vh_audio_exit_timeline_mark(&timeline,9,100)==-1);
    assert(vh_audio_exit_timeline_mark(NULL,0,100)==-1);
    assert(vh_audio_exit_timeline_mark(&timeline,0,0)==-1);
    assert(vh_audio_exit_timeline_get(NULL,0)==0);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_PLUS_OBSERVED,1000)==1);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_PLUS_OBSERVED,1001)==0);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_STOP_REQUESTED,1040)==1);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_WORKER_CLEANUP_ENTERED,1100)==1);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_AUDOUT_CLOSED,1130)==1);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_WORKER_JOINED,1160)==1);
    assert(vh_audio_exit_timeline_get(&timeline,VH_EXIT_PLUS_OBSERVED)==1000);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_exit_timeline_write_csv(&timeline,f)==5);
    assert(!fflush(f));
    rewind(f);
    expect_line(f,"event,guest_monotonic_ns\n");
    expect_line(f,"plus_observed,1000\n");
    expect_line(f,"stop_requested,1040\n");
    expect_line(f,"worker_cleanup_entered,1100\n");
    expect_line(f,"audout_closed,1130\n");
    expect_line(f,"worker_joined,1160\n");
    assert(fgetc(f)==EOF);
    assert(!fclose(f));
}

static void test_missing_worker_and_reset(void) {
    VhAudioExitTimeline timeline = {0};
    vh_audio_exit_timeline_reset(&timeline);
    assert(vh_audio_exit_timeline_mark(&timeline,VH_EXIT_WORKER_CLEANUP_ENTERED,900)==1);
    assert(vh_audio_exit_timeline_get(&timeline,VH_EXIT_PLUS_OBSERVED)==0);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_exit_timeline_write_csv(&timeline,f)==5);
    rewind(f);
    expect_line(f,"event,guest_monotonic_ns\n");
    expect_line(f,"plus_observed,0\n");
    expect_line(f,"stop_requested,0\n");
    expect_line(f,"worker_cleanup_entered,900\n");
    assert(!fclose(f));
    vh_audio_exit_timeline_reset(&timeline);
    for(unsigned i=0;i<VH_EXIT_EVENT_COUNT;i++)
        assert(vh_audio_exit_timeline_get(&timeline,i)==0);
    assert(vh_audio_exit_timeline_write_csv(NULL,stdout)<0);
    assert(vh_audio_exit_timeline_write_csv(&timeline,NULL)<0);
}

int main(void) {
    test_once_and_round_trip();
    test_missing_worker_and_reset();
    puts("Stage307 guest exit timeline tests passed");
    return 0;
}
