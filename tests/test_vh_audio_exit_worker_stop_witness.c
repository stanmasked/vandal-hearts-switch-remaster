#include "vh_audio_exit_worker_stop_witness.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_single_observation(void) {
    VhAudioExitWorkerStopWitness w={0};
    vh_audio_exit_worker_stop_reset(&w);
    assert(vh_audio_exit_worker_stop_read(&w)==0);
    assert(vh_audio_exit_worker_stop_mark(NULL,100)==-1);
    assert(vh_audio_exit_worker_stop_mark(&w,0)==-1);
    assert(vh_audio_exit_worker_stop_mark(&w,115500)==1);
    assert(vh_audio_exit_worker_stop_mark(&w,115600)==0);
    assert(vh_audio_exit_worker_stop_read(&w)==115500);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_exit_worker_stop_write_csv(&w,f)==1);
    rewind(f);
    char line[80]={0};
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,"event,guest_monotonic_ns\n")==0);
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,"worker_stop_observed,115500\n")==0);
    assert(fgetc(f)==EOF);
    assert(fclose(f)==0);
}
static void test_absent_marker_is_not_forged(void) {
    VhAudioExitWorkerStopWitness w={0};
    vh_audio_exit_worker_stop_reset(&w);
    FILE *f=tmpfile();
    assert(f);
    assert(vh_audio_exit_worker_stop_write_csv(&w,f)==1);
    rewind(f);
    char line[80]={0};
    assert(fgets(line,sizeof line,f));
    assert(fgets(line,sizeof line,f));
    assert(strcmp(line,"worker_stop_observed,0\n")==0);
    assert(fclose(f)==0);
    assert(vh_audio_exit_worker_stop_write_csv(NULL,stdout)<0);
    assert(vh_audio_exit_worker_stop_write_csv(&w,NULL)<0);
    assert(vh_audio_exit_worker_stop_read(NULL)==0);
    assert(vh_audio_exit_worker_stop_mark(&w,200)==1);
    vh_audio_exit_worker_stop_reset(&w);
    assert(vh_audio_exit_worker_stop_read(&w)==0);
}
int main(void) {
    test_single_observation();
    test_absent_marker_is_not_forged();
    puts("Stage317 worker-observed stop flag witness passed");
    return 0;
}
